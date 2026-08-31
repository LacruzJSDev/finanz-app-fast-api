import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.accounts.commands import AccountCommand, UpdateAccountCommand
from app.accounts.models import SPENDABLE_ACCOUNT_TYPES, Account, AccountTypeEnum
from app.shared.commands import UNSET


@dataclass
class GroupBalanceRow:
    """Fila cruda del agregado de saldo de un grupo. currency es None cuando el
    grupo no tiene ninguna cuenta activa: no hay divisa que deducir."""

    net_worth: int
    available: int
    account_count: int
    spendable_account_count: int
    currency: str | None


@dataclass
class AccountRepository:
    """Acceso a datos del dominio accounts."""

    db: Session

    def create_account(
        self, user_id: uuid.UUID, new_account: AccountCommand
    ) -> Account:
        # None aquí significa "no lo mandó el cliente" — se omite del INSERT
        # para que la propia columna aplique su server_default, en vez de
        # duplicar esos defaults a mano en Python.
        values: dict[str, str | int | AccountTypeEnum] = {}
        if new_account.type is not None:
            values["type"] = new_account.type
        if new_account.opening_balance is not None:
            values["opening_balance"] = new_account.opening_balance
        if new_account.currency is not None:
            values["currency"] = new_account.currency
        if new_account.color is not None:
            values["color"] = new_account.color
        if new_account.icon is not None:
            values["icon"] = new_account.icon

        account = Account(
            group_id=new_account.group_id,
            name=new_account.name,
            **values,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(account)
        self.db.flush()
        return account

    def get_accounts_by_group_id(self, group_id: uuid.UUID) -> list[Account]:
        accounts = (
            self.db.execute(select(Account).where(Account.group_id == group_id))
            .scalars()
            .all()
        )
        return list(accounts)

    def get_group_balance(self, group_id: uuid.UUID) -> GroupBalanceRow:
        is_spendable = Account.type.in_(SPENDABLE_ACCOUNT_TYPES)
        # ARCHITECTURE.md §8.3: un solo escaneo con FILTER en vez de encadenar
        # consultas; COALESCE porque SUM de cero filas es NULL.
        row = self.db.execute(
            select(
                func.coalesce(func.sum(Account.balance), 0),
                func.coalesce(func.sum(Account.balance).filter(is_spendable), 0),
                func.count(Account.id),
                func.count(Account.id).filter(is_spendable),
                # Divisa única por grupo (accounts.md §5): cualquier cuenta
                # activa sirve para deducirla.
                func.max(Account.currency),
            ).where(Account.group_id == group_id, Account.is_active.is_(True))
        ).one()

        # SUM sobre BIGINT devuelve NUMERIC, que psycopg entrega como Decimal.
        return GroupBalanceRow(
            net_worth=int(row[0]),
            available=int(row[1]),
            account_count=int(row[2]),
            spendable_account_count=int(row[3]),
            currency=row[4],
        )

    def get_account_by_id(self, account_id: uuid.UUID) -> Account | None:
        return self.db.execute(
            select(Account).where(Account.id == account_id)
        ).scalar_one_or_none()

    def update_account(
        self, account_id: uuid.UUID, account: UpdateAccountCommand
    ) -> Account:
        # UNSET es la marca de ausencia: un None que llega aquí es un null
        # explícito del cliente y sí se escribe (ARCHITECTURE.md §5.5).
        values: dict[str, str | bool | AccountTypeEnum | None] = {}
        if account.name is not UNSET:
            values["name"] = account.name
        if account.type is not UNSET:
            values["type"] = account.type
        if account.color is not UNSET:
            values["color"] = account.color
        if account.icon is not UNSET:
            values["icon"] = account.icon
        if account.is_active is not UNSET:
            values["is_active"] = account.is_active

        return self.db.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(**values)
            .returning(Account)
        ).scalar_one()
