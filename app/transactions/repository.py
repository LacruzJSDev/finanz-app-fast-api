import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.transactions.commands import TransactionRowCommand
from app.transactions.models import Transaction


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
