import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.payment_plans.commands import CreatePaymentPlanCommand
from app.payment_plans.models import PaymentPlan


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
