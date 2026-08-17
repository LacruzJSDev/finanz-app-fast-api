import uuid
from dataclasses import dataclass
from datetime import date as date_

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.payment_plans.commands import (
    CreatePaymentPlanCommand,
    UpdatePaymentPlanCommand,
)
from app.payment_plans.models import FrequencyUnitEnum, PaymentPlan
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

    def get_payment_plan_by_id(self, payment_plan_id: uuid.UUID) -> PaymentPlan | None:
        return self.db.execute(
            select(PaymentPlan).where(PaymentPlan.id == payment_plan_id)
        ).scalar_one_or_none()

    def update_payment_plan(
        self, payment_plan_id: uuid.UUID, command: UpdatePaymentPlanCommand
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
        if command.amount is not None:
            values["amount"] = command.amount
        if command.type is not None:
            values["type"] = command.type
        if command.category_id is not None:
            values["category_id"] = command.category_id
        if command.description is not None:
            values["description"] = command.description
        if command.next_due_date is not None:
            values["next_due_date"] = command.next_due_date
        if command.is_active is not None:
            values["is_active"] = command.is_active

        if command.is_recurring is not None:
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
            and command.frequency_interval is not None
        ):
            values["frequency_interval"] = command.frequency_interval
        if "frequency_unit" not in values and command.frequency_unit is not None:
            values["frequency_unit"] = command.frequency_unit
        if "end_date" not in values and command.end_date is not None:
            values["end_date"] = command.end_date

        return self.db.execute(
            update(PaymentPlan)
            .where(PaymentPlan.id == payment_plan_id)
            .values(**values)
            .returning(PaymentPlan)
        ).scalar_one()
