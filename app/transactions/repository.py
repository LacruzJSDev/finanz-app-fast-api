import uuid
from dataclasses import dataclass
from datetime import date as date_
from datetime import datetime, timezone

from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.orm import Session, aliased
from sqlalchemy.orm.util import AliasedClass

from app.accounts.models import Account
from app.categories.models import Category
from app.shared.commands import UNSET
from app.transactions.commands import (
    TransactionFilterCommand,
    TransactionRowCommand,
    UpdateTransactionCommand,
)
from app.transactions.models import Transaction, TransactionTypeEnum


@dataclass
class CategorySummaryRow:
    """Fila cruda del desglose por categoría raíz. Los nulos identifican al
    grupo de transacciones sin categoría."""

    root_category_id: uuid.UUID | None
    root_category_name: str | None
    income: int
    expense: int
    transaction_count: int


def _root_category_id(
    category: type[Category] | AliasedClass[Category],
) -> ColumnElement[uuid.UUID]:
    """Raíz de una categoría. La jerarquía es de dos niveles exactos
    (trg_check_category_depth), así que es un COALESCE y nunca una CTE
    recursiva (ARCHITECTURE.md §8.3)."""
    return func.coalesce(category.parent_id, category.id)


def build_filter_conditions(
    filters: TransactionFilterCommand,
) -> list[ColumnElement[bool]]:
    """Traduce los filtros a condiciones SQL, una sola vez para el listado y
    para los agregados: si cada consulta mantuviera su propio WHERE acabarían
    divergiendo y un resumen dejaría de describir las filas del listado
    (ARCHITECTURE.md §8.3). Exige el JOIN con accounts, porque transactions no
    tiene group_id propio.
    """
    conditions: list[ColumnElement[bool]] = [
        Account.group_id == filters.group_id,
        Transaction.deleted_at.is_(None),
    ]
    if filters.account_id is not None:
        conditions.append(Transaction.account_id == filters.account_id)
    if filters.category_id is not None:
        # Una raíz arrastra sus subcategorías; una subcategoría solo se
        # devuelve a sí misma (transactions.md §5).
        conditions.append(
            Transaction.category_id.in_(
                select(Category.id).where(
                    or_(
                        _root_category_id(Category) == filters.category_id,
                        Category.id == filters.category_id,
                    )
                )
            )
        )
    if filters.uncategorized:
        conditions.append(Transaction.category_id.is_(None))
    if filters.type is not None:
        conditions.append(Transaction.type == filters.type)
    if filters.date_from is not None:
        conditions.append(Transaction.date >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(Transaction.date <= filters.date_to)
    if filters.q:
        conditions.append(Transaction.notes.ilike(f"%{filters.q}%"))
    return conditions


@dataclass
class TransactionRepository:
    """Acceso a datos del dominio transactions."""

    db: Session

    def create_transaction(
        self, user_id: uuid.UUID | None, row: TransactionRowCommand
    ) -> Transaction:
        transaction = Transaction(
            account_id=row.account_id,
            to_account_id=row.to_account_id,
            category_id=row.category_id,
            transfer_group_id=row.transfer_group_id,
            payment_plan_id=row.payment_plan_id,
            payment_plan_occurrence_id=row.payment_plan_occurrence_id,
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

    def get_filtered_transactions(
        self, filters: TransactionFilterCommand, limit: int, offset: int
    ) -> tuple[list[Transaction], int]:
        conditions = build_filter_conditions(filters)
        total = self.db.execute(
            select(func.count())
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(*conditions)
        ).scalar_one()
        transactions = (
            self.db.execute(
                select(Transaction)
                .join(Account, Account.id == Transaction.account_id)
                .where(*conditions)
                .order_by(Transaction.date.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        return list(transactions), total

    def get_category_summary(
        self, filters: TransactionFilterCommand
    ) -> list[CategorySummaryRow]:
        category = aliased(Category)
        root = aliased(Category)
        income = Transaction.type == TransactionTypeEnum.INCOME
        expense = Transaction.type == TransactionTypeEnum.EXPENSE
        rows = self.db.execute(
            select(
                root.id,
                root.name,
                func.coalesce(func.sum(Transaction.amount).filter(income), 0),
                func.coalesce(func.sum(Transaction.amount).filter(expense), 0),
                func.count(Transaction.id),
            )
            # Sin select_from explícito, el FROM lo deduciría de la primera
            # columna — que aquí es el alias de categories, no transactions.
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            # outerjoin: lo no categorizado también cuenta, agrupado en la
            # fila de raíz nula (transactions.md §4.B).
            .outerjoin(category, category.id == Transaction.category_id)
            .outerjoin(root, root.id == _root_category_id(category))
            .where(*build_filter_conditions(filters))
            .where(Transaction.type != TransactionTypeEnum.TRANSFER)
            .group_by(root.id, root.name)
            .order_by(root.name)
        ).all()

        # SUM sobre BIGINT devuelve NUMERIC, que psycopg entrega como Decimal.
        return [
            CategorySummaryRow(
                root_category_id=row[0],
                root_category_name=row[1],
                income=int(row[2]),
                expense=int(row[3]),
                transaction_count=int(row[4]),
            )
            for row in rows
        ]

    def get_spent_on_date(self, filters: TransactionFilterCommand) -> tuple[int, int]:
        """Magnitud gastada y número de movimientos. Los gastos se almacenan
        en negativo y aquí salen en positivo (transactions.md §5)."""
        row = self.db.execute(
            select(
                func.coalesce(func.sum(Transaction.amount), 0),
                func.count(Transaction.id),
            )
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(*build_filter_conditions(filters))
        ).one()
        return abs(int(row[0])), int(row[1])

    def get_transaction_by_id(self, transaction_id: uuid.UUID) -> Transaction | None:
        return self.db.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        ).scalar_one_or_none()

    def update_transaction(
        self,
        transaction_id: uuid.UUID,
        command: UpdateTransactionCommand,
        user_id: uuid.UUID,
    ) -> Transaction:
        # La marca de ausencia es UNSET, no None: un None que llega aquí es un
        # null explícito del cliente y sí debe escribirse (ARCHITECTURE.md §5.5).
        values: dict[
            str, int | uuid.UUID | date_ | str | TransactionTypeEnum | None
        ] = {}
        if command.amount is not UNSET:
            values["amount"] = command.amount
        if command.type is not UNSET:
            values["type"] = command.type
        if command.category_id is not UNSET:
            values["category_id"] = command.category_id
        if command.date is not UNSET:
            values["date"] = command.date
        if command.notes is not UNSET:
            values["notes"] = command.notes
        values["updated_by"] = user_id

        return self.db.execute(
            update(Transaction)
            .where(Transaction.id == transaction_id)
            .values(**values)
            .returning(Transaction)
        ).scalar_one()

    def delete_transaction(self, transaction_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self.db.execute(
            update(Transaction)
            .where(Transaction.id == transaction_id)
            .values(deleted_at=datetime.now(timezone.utc), updated_by=user_id)
        )
