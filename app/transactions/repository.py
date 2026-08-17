import uuid
from dataclasses import dataclass
from datetime import date as date_

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.transactions.commands import TransactionRowCommand, UpdateTransactionCommand
from app.transactions.models import Transaction, TransactionTypeEnum


@dataclass
class TransactionRepository:
    """Acceso a datos del dominio transactions."""

    db: Session

    def create_transaction(
        self, user_id: uuid.UUID, row: TransactionRowCommand
    ) -> Transaction:
        transaction = Transaction(
            account_id=row.account_id,
            to_account_id=row.to_account_id,
            category_id=row.category_id,
            transfer_group_id=row.transfer_group_id,
            amount=row.amount,
            type=row.type,
            date=row.date,
            notes=row.notes,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def get_transactions_by_account_id(
        self, account_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Transaction], int]:
        base_filter = (
            Transaction.account_id == account_id,
            Transaction.deleted_at.is_(None),
        )
        total = self.db.execute(
            select(func.count()).select_from(Transaction).where(*base_filter)
        ).scalar_one()
        transactions = (
            self.db.execute(
                select(Transaction)
                .where(*base_filter)
                .order_by(Transaction.date.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        return list(transactions), total

    def get_transaction_by_id(self, transaction_id: uuid.UUID) -> Transaction | None:
        return self.db.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        ).scalar_one_or_none()

    def update_transaction(
        self, transaction_id: uuid.UUID, command: UpdateTransactionCommand
    ) -> Transaction:
        values: dict[str, int | uuid.UUID | date_ | str | TransactionTypeEnum] = {}
        if command.amount is not None:
            values["amount"] = command.amount
        if command.type is not None:
            values["type"] = command.type
        if command.category_id is not None:
            values["category_id"] = command.category_id
        if command.date is not None:
            values["date"] = command.date
        if command.notes is not None:
            values["notes"] = command.notes

        return self.db.execute(
            update(Transaction)
            .where(Transaction.id == transaction_id)
            .values(**values)
            .returning(Transaction)
        ).scalar_one()
