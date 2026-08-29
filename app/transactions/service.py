import uuid
from dataclasses import dataclass

from app.accounts.repository import AccountRepository
from app.categories.repository import CategoryRepository
from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError
from app.transactions.commands import (
    CreateTransactionCommand,
    DailySpendCommand,
    TransactionFilterCommand,
    TransactionRowCommand,
    UpdateTransactionCommand,
)
from app.transactions.models import TransactionTypeEnum
from app.transactions.repository import TransactionRepository
from app.transactions.schemas import (
    CategorySummaryRead,
    DailySpendRead,
    TransactionRead,
)


@dataclass
class PaginatedTransactions:
    items: list[TransactionRead]
    total: int


@dataclass
class TransactionService:
    """Lógica de negocio del dominio transactions."""

    transaction_repo: TransactionRepository
    account_repo: AccountRepository
    category_repo: CategoryRepository

    def get_transactions(
        self, account_id: uuid.UUID, limit: int, offset: int
    ) -> PaginatedTransactions:
        transactions, total = self.transaction_repo.get_transactions_by_account_id(
            account_id, limit, offset
        )
        items = [TransactionRead.model_validate(t) for t in transactions]
        return PaginatedTransactions(items=items, total=total)

    def get_filtered_transactions(
        self, filters: TransactionFilterCommand, limit: int, offset: int
    ) -> PaginatedTransactions:
        self._check_filter_scope(filters.group_id, filters.account_id)
        self._check_category(filters.category_id, filters.group_id)
        transactions, total = self.transaction_repo.get_filtered_transactions(
            filters, limit, offset
        )
        items = [TransactionRead.model_validate(t) for t in transactions]
        return PaginatedTransactions(items=items, total=total)

    def get_category_summary(
        self, filters: TransactionFilterCommand
    ) -> list[CategorySummaryRead]:
        self._check_filter_scope(filters.group_id, filters.account_id)
        self._check_category(filters.category_id, filters.group_id)
        rows = self.transaction_repo.get_category_summary(filters)
        return [
            CategorySummaryRead(
                root_category_id=row.root_category_id,
                root_category_name=row.root_category_name,
                income=row.income,
                expense=row.expense,
                transaction_count=row.transaction_count,
            )
            for row in rows
        ]

    def get_daily_spend(self, command: DailySpendCommand) -> DailySpendRead:
        self._check_filter_scope(command.group_id, command.account_id)
        # Un día concreto es el mismo juego de filtros con el rango cerrado
        # sobre una sola fecha, de modo que "gastado hoy" cuadra con lo que
        # devuelve el listado de ese día (ARCHITECTURE.md §8.3).
        filters = TransactionFilterCommand(
            group_id=command.group_id,
            account_id=command.account_id,
            type=TransactionTypeEnum.EXPENSE,
            date_from=command.date,
            date_to=command.date,
        )
        spent, transaction_count = self.transaction_repo.get_spent_on_date(filters)
        return DailySpendRead(
            date=command.date, spent=spent, transaction_count=transaction_count
        )

    def _check_filter_scope(
        self, group_id: uuid.UUID, account_id: uuid.UUID | None
    ) -> None:
        """Sin esto, un miembro legítimo del grupo leería movimientos de otro
        pasando un account_id ajeno (transactions.md §5)."""
        if account_id is None:
            return
        account = self.account_repo.get_account_by_id(account_id)
        if account is None or account.group_id != group_id:
            raise ConflictError("La cuenta no pertenece al grupo")

    def get_transaction(
        self, account_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> TransactionRead:
        transaction = self.transaction_repo.get_transaction_by_id(transaction_id)
        if (
            transaction is None
            or transaction.account_id != account_id
            or transaction.deleted_at is not None
        ):
            raise NotFoundError("La transacción no existe")
        return TransactionRead.model_validate(transaction)

    def update_transaction(
        self,
        account_id: uuid.UUID,
        transaction_id: uuid.UUID,
        command: UpdateTransactionCommand,
    ) -> TransactionRead:
        fields = (
            command.amount,
            command.type,
            command.category_id,
            command.date,
            command.notes,
        )
        if all(field is None for field in fields):
            raise BadRequestError("Debes incluir al menos un campo para actualizar")

        transaction = self.transaction_repo.get_transaction_by_id(transaction_id)
        if (
            transaction is None
            or transaction.account_id != account_id
            or transaction.deleted_at is not None
        ):
            raise NotFoundError("La transacción no existe")

        if (
            command.type is not None
            and transaction.type == TransactionTypeEnum.TRANSFER
        ):
            raise ConflictError("No se puede cambiar el tipo de una transferencia")
        effective_type = command.type or transaction.type

        if command.category_id is not None:
            if effective_type == TransactionTypeEnum.TRANSFER:
                raise ConflictError("Una transferencia no admite category_id")
            account = self.account_repo.get_account_by_id(transaction.account_id)
            if account is None:
                raise NotFoundError("La transacción no existe")
            self._check_category(command.category_id, account.group_id)

        if command.amount is not None or command.type is not None:
            magnitude = (
                command.amount
                if command.amount is not None
                else abs(transaction.amount)
            )
            if effective_type == TransactionTypeEnum.TRANSFER:
                sign = 1 if transaction.amount > 0 else -1
            else:
                sign = 1 if effective_type == TransactionTypeEnum.INCOME else -1
            command.amount = sign * magnitude

        updated_transaction = self.transaction_repo.update_transaction(
            transaction_id, command
        )
        return TransactionRead.model_validate(updated_transaction)

    def delete_transaction(
        self, account_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> None:
        transaction = self.transaction_repo.get_transaction_by_id(transaction_id)
        if (
            transaction is None
            or transaction.account_id != account_id
            or transaction.deleted_at is not None
        ):
            raise NotFoundError("La transacción no existe")
        self.transaction_repo.delete_transaction(transaction_id)

    def _check_category(
        self, category_id: uuid.UUID | None, group_id: uuid.UUID
    ) -> None:
        if category_id is None:
            return
        category = self.category_repo.get_category_by_id(category_id)
        if category is None or category.group_id != group_id:
            raise ConflictError("La categoría no pertenece al grupo de la cuenta")

    def create_transaction(
        self, user_id: uuid.UUID | None, command: CreateTransactionCommand
    ) -> TransactionRead:
        self._check_category(command.category_id, command.group_id)

        if command.type == TransactionTypeEnum.TRANSFER:
            return self._create_transfer(user_id, command)

        signed_amount = (
            command.amount
            if command.type == TransactionTypeEnum.INCOME
            else -command.amount
        )
        row = TransactionRowCommand(
            account_id=command.account_id,
            to_account_id=None,
            category_id=command.category_id,
            transfer_group_id=None,
            amount=signed_amount,
            type=command.type,
            date=command.date,
            notes=command.notes,
            payment_plan_id=command.payment_plan_id,
        )
        transaction = self.transaction_repo.create_transaction(user_id, row)
        return TransactionRead.model_validate(transaction)

    def _create_transfer(
        self, user_id: uuid.UUID | None, command: CreateTransactionCommand
    ) -> TransactionRead:
        to_account_id = command.to_account_id
        if to_account_id is None:
            # El schema de entrada ya lo exige para type=transfer; esta
            # comprobación es solo para que pyright estreche el tipo.
            raise ConflictError("Una transferencia necesita to_account_id")
        if to_account_id == command.account_id:
            raise ConflictError(
                "El destino de la transferencia no puede ser la misma cuenta"
            )

        to_account = self.account_repo.get_account_by_id(to_account_id)
        if to_account is None or to_account.group_id != command.group_id:
            raise ConflictError("La cuenta destino no pertenece al mismo grupo")

        transfer_group_id = uuid.uuid4()

        origin_row = TransactionRowCommand(
            account_id=command.account_id,
            to_account_id=to_account_id,
            category_id=None,
            transfer_group_id=transfer_group_id,
            amount=-command.amount,
            type=command.type,
            date=command.date,
            notes=command.notes,
            payment_plan_id=command.payment_plan_id,
        )
        destination_row = TransactionRowCommand(
            account_id=to_account_id,
            to_account_id=command.account_id,
            category_id=None,
            transfer_group_id=transfer_group_id,
            amount=command.amount,
            type=command.type,
            date=command.date,
            notes=command.notes,
            payment_plan_id=command.payment_plan_id,
        )
        origin_transaction = self.transaction_repo.create_transaction(
            user_id, origin_row
        )
        self.transaction_repo.create_transaction(user_id, destination_row)
        return TransactionRead.model_validate(origin_transaction)
