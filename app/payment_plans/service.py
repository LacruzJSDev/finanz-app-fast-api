import uuid
from dataclasses import dataclass

from app.accounts.repository import AccountRepository
from app.categories.repository import CategoryRepository
from app.payment_plans.commands import CreatePaymentPlanCommand
from app.payment_plans.repository import PaymentPlanRepository
from app.payment_plans.schemas import PaymentPlanRead
from app.shared.exceptions import ConflictError, NotFoundError
from app.transactions.models import TransactionTypeEnum


@dataclass
class PaymentPlanService:
    """Lógica de negocio del dominio payment_plans."""

    payment_plan_repo: PaymentPlanRepository
    account_repo: AccountRepository
    category_repo: CategoryRepository

    def _check_category(
        self, category_id: uuid.UUID | None, group_id: uuid.UUID
    ) -> None:
        if category_id is None:
            return
        category = self.category_repo.get_category_by_id(category_id)
        if category is None or category.group_id != group_id:
            raise ConflictError("La categoría no pertenece al grupo de la cuenta")

    def create_payment_plan(
        self, user_id: uuid.UUID, command: CreatePaymentPlanCommand
    ) -> PaymentPlanRead:
        self._check_category(command.category_id, command.group_id)

        if command.type == TransactionTypeEnum.TRANSFER:
            to_account_id = command.to_account_id
            if to_account_id is None:
                raise ConflictError("Una transferencia necesita to_account_id")
            if to_account_id == command.account_id:
                raise ConflictError(
                    "El destino de la transferencia no puede ser la misma cuenta"
                )
            to_account = self.account_repo.get_account_by_id(to_account_id)
            if to_account is None or to_account.group_id != command.group_id:
                raise ConflictError("La cuenta destino no pertenece al mismo grupo")

        payment_plan = self.payment_plan_repo.create_payment_plan(user_id, command)
        return PaymentPlanRead.model_validate(payment_plan)

    def get_payment_plans(self, account_id: uuid.UUID) -> list[PaymentPlanRead]:
        payment_plans = self.payment_plan_repo.get_payment_plans_by_account_id(
            account_id
        )
        return [PaymentPlanRead.model_validate(p) for p in payment_plans]

    def get_payment_plan(
        self, account_id: uuid.UUID, payment_plan_id: uuid.UUID
    ) -> PaymentPlanRead:
        payment_plan = self.payment_plan_repo.get_payment_plan_by_id(payment_plan_id)
        if payment_plan is None or payment_plan.account_id != account_id:
            raise NotFoundError("El plan no existe")
        return PaymentPlanRead.model_validate(payment_plan)
