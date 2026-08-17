import uuid
from dataclasses import dataclass

from app.accounts.repository import AccountRepository
from app.categories.repository import CategoryRepository
from app.shared.exceptions import ConflictError, NotFoundError
from app.transactions.commands import CreateTransactionCommand, TransactionRowCommand
from app.transactions.models import TransactionTypeEnum
from app.transactions.repository import TransactionRepository
from app.transactions.schemas import TransactionRead


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

    def _check_category(
        self, category_id: uuid.UUID | None, group_id: uuid.UUID
    ) -> None:
        if category_id is None:
            return
        category = self.category_repo.get_category_by_id(category_id)
        if category is None or category.group_id != group_id:
            raise ConflictError("La categoría no pertenece al grupo de la cuenta")

    def create_transaction(
        self, user_id: uuid.UUID, command: CreateTransactionCommand
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
        )
        transaction = self.transaction_repo.create_transaction(user_id, row)
        return TransactionRead.model_validate(transaction)

    def _create_transfer(
        self, user_id: uuid.UUID, command: CreateTransactionCommand
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
        )
        origin_transaction = self.transaction_repo.create_transaction(
            user_id, origin_row
        )
        self.transaction_repo.create_transaction(user_id, destination_row)
        return TransactionRead.model_validate(origin_transaction)
