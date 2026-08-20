import calendar
import logging
import logging.config
import uuid
from datetime import date, timedelta

from sqlalchemy import select

import app.db_registry
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


def _advance_date(current: date, interval: int, unit: FrequencyUnitEnum) -> date:
    if unit == FrequencyUnitEnum.DAY:
        return current + timedelta(days=interval)
    if unit == FrequencyUnitEnum.WEEK:
        return current + timedelta(weeks=interval)

    months_to_add = interval if unit == FrequencyUnitEnum.MONTH else interval * 12
    total_months = current.month - 1 + months_to_add
    year = current.year + total_months // 12
    month = total_months % 12 + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _process_due_plan(payment_plan_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        payment_plan_repo = PaymentPlanRepository(db)
        account_repo = AccountRepository(db)
        transaction_service = TransactionService(
            TransactionRepository(db), account_repo, CategoryRepository(db)
        )

        plan = payment_plan_repo.get_payment_plan_by_id(payment_plan_id)
        if plan is None or not plan.is_active:
            return

        account = account_repo.get_account_by_id(plan.account_id)
        if account is None:
            return

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
        )
        transaction_service.create_transaction(None, command)

        if plan.is_recurring:
            assert plan.frequency_interval is not None
            assert plan.frequency_unit is not None
            next_due_date = _advance_date(
                plan.next_due_date, plan.frequency_interval, plan.frequency_unit
            )
            if plan.end_date is not None and next_due_date > plan.end_date:
                payment_plan_repo.deactivate_payment_plan(plan.id)
            else:
                payment_plan_repo.advance_next_due_date(plan.id, next_due_date)
        else:
            payment_plan_repo.deactivate_payment_plan(plan.id)

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("No se pudo materializar el plan de pago %s", payment_plan_id)
    finally:
        db.close()


def run_due_payment_plans() -> None:
    db = SessionLocal()
    try:
        today = date.today()
        due_ids = (
            db.execute(
                select(PaymentPlan.id).where(
                    PaymentPlan.is_active.is_(True),
                    PaymentPlan.next_due_date <= today,
                )
            )
            .scalars()
            .all()
        )
    finally:
        db.close()

    logger.info("Planes de pago vencidos a procesar: %d", len(due_ids))
    for payment_plan_id in due_ids:
        _process_due_plan(payment_plan_id)


if __name__ == "__main__":
    logging.config.dictConfig(build_log_config())
    run_due_payment_plans()
