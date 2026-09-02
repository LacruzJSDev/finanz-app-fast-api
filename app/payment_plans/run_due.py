import calendar
import logging
import logging.config
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.db_registry
from app.account_groups.models import AccountGroup
from app.account_groups.repository import AccountGroupsRepository
from app.accounts.models import Account
from app.accounts.repository import AccountRepository
from app.categories.repository import CategoryRepository
from app.database import SessionLocal
from app.logging_config import build_log_config
from app.payment_plans.models import FrequencyUnitEnum, PaymentPlan
from app.payment_plans.repository import PaymentPlanRepository
from app.transactions.commands import CreateTransactionCommand
from app.transactions.repository import TransactionRepository
from app.transactions.service import TransactionService

# Igual que en alembic/env.py: importar db_registry registra todos los
# modelos en Base.metadata, o SQLAlchemy no encuentra tablas como users al
# resolver las ForeignKey de transactions durante el flush. El assert es
# solo para que ruff no marque el import como no usado.
assert app.db_registry

logger = logging.getLogger(__name__)


def advance_scheduled_date(
    current: date,
    interval: int,
    unit: FrequencyUnitEnum,
    anchor_day: int | None = None,
) -> date:
    if unit == FrequencyUnitEnum.DAY:
        return current + timedelta(days=interval)
    if unit == FrequencyUnitEnum.WEEK:
        return current + timedelta(weeks=interval)

    months_to_add = interval if unit == FrequencyUnitEnum.MONTH else interval * 12
    total_months = current.month - 1 + months_to_add
    year = current.year + total_months // 12
    month = total_months % 12 + 1
    day = min(anchor_day or current.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def payment_plan_occurrence_id(
    payment_plan_id: uuid.UUID, scheduled_for: date
) -> uuid.UUID:
    """ID estable de una ocurrencia, independiente del proceso que la ejecute."""
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"finanzapp:payment-plan:{payment_plan_id}:{scheduled_for.isoformat()}",
    )


def process_due_plan(payment_plan_id: uuid.UUID, today: date | None = None) -> None:
    db = SessionLocal()
    processing_date = today or date.today()
    try:
        payment_plan_repo = PaymentPlanRepository(db)
        account_repo = AccountRepository(db)
        transaction_service = TransactionService(
            TransactionRepository(db), account_repo, CategoryRepository(db)
        )

        # El lock serializa dos instancias del cron para el mismo plan. La
        # segunda espera al commit de la primera y debe volver a comprobar
        # estado y vencimiento: el listado inicial puede haber quedado viejo.
        plan = payment_plan_repo.get_payment_plan_by_id(
            payment_plan_id, for_update=True
        )
        if plan is None or not plan.is_active or plan.next_due_date > processing_date:
            return

        account = account_repo.get_account_by_id(plan.account_id)
        if account is None or not account.is_active:
            return

        # payment_plans.md §5: archivar la cuenta o el grupo suspende sus
        # planes. Se revalida aquí y no solo en la selección porque cada plan
        # se procesa en su propia sesión, después de la consulta.
        group = AccountGroupsRepository(db).get_group_by_id(account.group_id)
        if group is None or not group.is_active:
            return

        # Determinista: dos crons que intenten materializar el mismo
        # vencimiento generan el mismo identificador, y el índice único de
        # transactions actúa como última línea de defensa frente a duplicados.
        occurrence_id = payment_plan_occurrence_id(plan.id, plan.next_due_date)
        command = CreateTransactionCommand(
            account_id=plan.account_id,
            group_id=account.group_id,
            type=plan.type,
            amount=plan.amount,
            category_id=plan.category_id,
            to_account_id=plan.to_account_id,
            date=plan.next_due_date,
            notes=plan.description,
            payment_plan_id=plan.id,
            payment_plan_occurrence_id=occurrence_id,
        )
        transaction_service.create_transaction(None, command)

        if plan.is_recurring:
            assert plan.frequency_interval is not None
            assert plan.frequency_unit is not None
            next_due_date = advance_scheduled_date(
                plan.next_due_date,
                plan.frequency_interval,
                plan.frequency_unit,
                plan.recurrence_anchor_day,
            )
            if plan.end_date is not None and next_due_date > plan.end_date:
                payment_plan_repo.deactivate_payment_plan(plan.id)
            else:
                payment_plan_repo.advance_next_due_date(plan.id, next_due_date)
        else:
            payment_plan_repo.deactivate_payment_plan(plan.id)

        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning(
            "Ocurrencia de plan ya materializada o inválida",
            extra={
                "payment_plan_id": str(payment_plan_id),
                "event": "payment_plan_materialization_duplicate",
            },
            exc_info=True,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "No se pudo materializar el plan de pago",
            extra={
                "payment_plan_id": str(payment_plan_id),
                "event": "payment_plan_materialization_failed",
            },
        )
    finally:
        db.close()


def due_plan_ids(db: Session, today: date) -> list[uuid.UUID]:
    """Planes vencidos que sí deben materializarse hoy.

    El JOIN no es decorativo: sin él, archivar un grupo o una cuenta no
    detendría sus planes, y el cron seguiría creando transacciones y moviendo
    saldos dentro de algo que el usuario dio por cerrado (payment_plans.md §5).
    """
    return list(
        db.execute(
            select(PaymentPlan.id)
            .join(Account, Account.id == PaymentPlan.account_id)
            .join(AccountGroup, AccountGroup.id == Account.group_id)
            .where(
                PaymentPlan.is_active.is_(True),
                Account.is_active.is_(True),
                AccountGroup.is_active.is_(True),
                PaymentPlan.next_due_date <= today,
            )
        )
        .scalars()
        .all()
    )


def run_due_payment_plans() -> None:
    db = SessionLocal()
    try:
        due_ids = due_plan_ids(db, date.today())
    finally:
        db.close()

    logger.info("Planes de pago vencidos a procesar: %d", len(due_ids))
    for payment_plan_id in due_ids:
        process_due_plan(payment_plan_id)


if __name__ == "__main__":
    logging.config.dictConfig(build_log_config())
    run_due_payment_plans()
