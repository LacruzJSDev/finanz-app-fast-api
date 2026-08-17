import uuid
from dataclasses import dataclass

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
