import uuid
from dataclasses import dataclass
from datetime import date as date_

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.payment_plans.commands import (
    CreatePaymentPlanCommand,
    UpdatePaymentPlanCommand,
)
from app.payment_plans.models import FrequencyUnitEnum, PaymentPlan
from app.shared.commands import UNSET
from app.transactions.models import TransactionTypeEnum


@dataclass
class PaymentPlanRepository:
    """Acceso a datos del dominio payment_plans."""

    db: Session

    def create_payment_plan(
        self, user_id: uuid.UUID, command: CreatePaymentPlanCommand
    ) -> PaymentPlan:
        payment_plan = PaymentPlan(
            account_id=command.account_id,
            to_account_id=command.to_account_id,
            category_id=command.category_id,
            type=command.type,
            amount=command.amount,
            description=command.description,
            next_due_date=command.next_due_date,
            recurrence_anchor_day=(
                command.next_due_date.day if command.is_recurring else None
            ),
            end_date=command.end_date,
            is_recurring=command.is_recurring,
            frequency_interval=command.frequency_interval,
            frequency_unit=command.frequency_unit,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(payment_plan)
        self.db.flush()
        return payment_plan

    def get_payment_plans_by_account_id(
        self, account_id: uuid.UUID
    ) -> list[PaymentPlan]:
        payment_plans = (
            self.db.execute(
                select(PaymentPlan).where(PaymentPlan.account_id == account_id)
            )
            .scalars()
            .all()
        )
        return list(payment_plans)

    def get_upcoming_by_group(
        self, group_id: uuid.UUID, until: date_
    ) -> list[PaymentPlan]:
        # payment_plans.md §4: sin cota inferior a propósito — un vencimiento
        # ya pasado que el cron todavía no ha materializado sigue pendiente.
        payment_plans = (
            self.db.execute(
                select(PaymentPlan)
                .join(Account, Account.id == PaymentPlan.account_id)
                .where(
                    Account.group_id == group_id,
                    PaymentPlan.is_active.is_(True),
                    PaymentPlan.next_due_date <= until,
                )
                .order_by(PaymentPlan.next_due_date)
            )
            .scalars()
            .all()
        )
        return list(payment_plans)

    def get_payday_plan(self, group_id: uuid.UUID) -> PaymentPlan | None:
        # payment_plans.md §5: el ancla de cobro se deriva por convención, sin
        # columna que la marque (ADR-0003). El tercer criterio de orden solo
        # da un desempate estable si fecha e importe coinciden.
        return self.db.execute(
            select(PaymentPlan)
            .join(Account, Account.id == PaymentPlan.account_id)
            .where(
                Account.group_id == group_id,
                PaymentPlan.is_active.is_(True),
                PaymentPlan.type == TransactionTypeEnum.INCOME,
                PaymentPlan.is_recurring.is_(True),
            )
            .order_by(
                PaymentPlan.next_due_date,
                PaymentPlan.amount.desc(),
                PaymentPlan.id,
            )
            .limit(1)
        ).scalar_one_or_none()

    def get_payment_plan_by_id(
        self, payment_plan_id: uuid.UUID, *, for_update: bool = False
    ) -> PaymentPlan | None:
        statement = select(PaymentPlan).where(PaymentPlan.id == payment_plan_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.execute(statement).scalar_one_or_none()

    def update_payment_plan(
        self,
        payment_plan_id: uuid.UUID,
        command: UpdatePaymentPlanCommand,
        user_id: uuid.UUID,
    ) -> PaymentPlan:
        values: dict[
            str,
            int
            | uuid.UUID
            | str
            | date_
            | bool
            | TransactionTypeEnum
            | FrequencyUnitEnum
            | None,
        ] = {}
        if command.amount is not UNSET:
            values["amount"] = command.amount
        if command.type is not UNSET:
            values["type"] = command.type
        if command.category_id is not UNSET:
            values["category_id"] = command.category_id
        if command.description is not UNSET:
            values["description"] = command.description
        if command.next_due_date is not UNSET:
            values["next_due_date"] = command.next_due_date
        if command.recurrence_anchor_day is not UNSET:
            values["recurrence_anchor_day"] = command.recurrence_anchor_day
        if command.is_active is not UNSET:
            values["is_active"] = command.is_active

        if command.is_recurring is not UNSET:
            values["is_recurring"] = command.is_recurring
            if command.is_recurring is False:
                # Apagar is_recurring limpia la periodicidad: el schema ya
                # exige que el cliente no mande nada de esto en la misma
                # petición, así que estos tres campos parten de None aquí.
                values["frequency_interval"] = None
                values["frequency_unit"] = None
                values["end_date"] = None

        if (
            "frequency_interval" not in values
            and command.frequency_interval is not UNSET
        ):
            values["frequency_interval"] = command.frequency_interval
        if "frequency_unit" not in values and command.frequency_unit is not UNSET:
            values["frequency_unit"] = command.frequency_unit
        if "end_date" not in values and command.end_date is not UNSET:
            values["end_date"] = command.end_date
        values["updated_by"] = user_id

        return self.db.execute(
            update(PaymentPlan)
            .where(PaymentPlan.id == payment_plan_id)
            .values(**values)
            .returning(PaymentPlan)
        ).scalar_one()

    def advance_next_due_date(
        self, payment_plan_id: uuid.UUID, next_due_date: date_
    ) -> None:
        self.db.execute(
            update(PaymentPlan)
            .where(PaymentPlan.id == payment_plan_id)
            .values(next_due_date=next_due_date)
        )

    def deactivate_payment_plan(self, payment_plan_id: uuid.UUID) -> None:
        self.db.execute(
            update(PaymentPlan)
            .where(PaymentPlan.id == payment_plan_id)
            .values(is_active=False)
        )
