import uuid
from dataclasses import dataclass
from datetime import date as date_

from app.accounts.repository import AccountRepository
from app.categories.repository import CategoryRepository
from app.payment_plans.commands import (
    CreatePaymentPlanCommand,
    UpdatePaymentPlanCommand,
)
from app.payment_plans.repository import PaymentPlanRepository
from app.payment_plans.schemas import PaymentPlanRead
from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError
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

    def get_upcoming_payment_plans(
        self, group_id: uuid.UUID, until: date_
    ) -> list[PaymentPlanRead]:
        payment_plans = self.payment_plan_repo.get_upcoming_by_group(group_id, until)
        return [PaymentPlanRead.model_validate(p) for p in payment_plans]

    def get_payday_plan(self, group_id: uuid.UUID) -> PaymentPlanRead | None:
        # payment_plans.md §5: un grupo sin ingreso recurrente activo no es un
        # error, el ancla simplemente no existe.
        payment_plan = self.payment_plan_repo.get_payday_plan(group_id)
        if payment_plan is None:
            return None
        return PaymentPlanRead.model_validate(payment_plan)

    def get_payment_plan(
        self, account_id: uuid.UUID, payment_plan_id: uuid.UUID
    ) -> PaymentPlanRead:
        payment_plan = self.payment_plan_repo.get_payment_plan_by_id(payment_plan_id)
        if payment_plan is None or payment_plan.account_id != account_id:
            raise NotFoundError("El plan no existe")
        return PaymentPlanRead.model_validate(payment_plan)

    def update_payment_plan(
        self,
        account_id: uuid.UUID,
        payment_plan_id: uuid.UUID,
        command: UpdatePaymentPlanCommand,
    ) -> PaymentPlanRead:
        fields = (
            command.amount,
            command.type,
            command.category_id,
            command.description,
            command.next_due_date,
            command.end_date,
            command.is_recurring,
            command.frequency_interval,
            command.frequency_unit,
            command.is_active,
        )
        if all(field is None for field in fields):
            raise BadRequestError("Debes incluir al menos un campo para actualizar")

        payment_plan = self.payment_plan_repo.get_payment_plan_by_id(payment_plan_id)
        if payment_plan is None or payment_plan.account_id != account_id:
            raise NotFoundError("El plan no existe")

        if (
            command.type is not None
            and payment_plan.type == TransactionTypeEnum.TRANSFER
        ):
            raise ConflictError("No se puede cambiar el tipo de una transferencia")
        effective_type = command.type or payment_plan.type

        if command.category_id is not None:
            if effective_type == TransactionTypeEnum.TRANSFER:
                raise ConflictError("Una transferencia no admite category_id")
            account = self.account_repo.get_account_by_id(payment_plan.account_id)
            if account is None:
                raise NotFoundError("El plan no existe")
            self._check_category(command.category_id, account.group_id)

        if command.is_recurring is False:
            effective_is_recurring = False
            effective_frequency_interval = None
            effective_frequency_unit = None
            effective_end_date = None
        else:
            effective_is_recurring = (
                command.is_recurring
                if command.is_recurring is not None
                else payment_plan.is_recurring
            )
            effective_frequency_interval = (
                command.frequency_interval
                if command.frequency_interval is not None
                else payment_plan.frequency_interval
            )
            effective_frequency_unit = (
                command.frequency_unit
                if command.frequency_unit is not None
                else payment_plan.frequency_unit
            )
            effective_end_date = (
                command.end_date
                if command.end_date is not None
                else payment_plan.end_date
            )

        effective_next_due_date = (
            command.next_due_date
            if command.next_due_date is not None
            else payment_plan.next_due_date
        )

        if effective_is_recurring and (
            effective_frequency_interval is None or effective_frequency_unit is None
        ):
            raise ConflictError(
                "Un plan recurrente necesita frequency_interval y frequency_unit"
            )
        if (
            effective_end_date is not None
            and effective_end_date < effective_next_due_date
        ):
            raise ConflictError("end_date no puede ser anterior a next_due_date")

        updated_payment_plan = self.payment_plan_repo.update_payment_plan(
            payment_plan_id, command
        )
        return PaymentPlanRead.model_validate(updated_payment_plan)
