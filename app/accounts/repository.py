import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.accounts.commands import AccountCommand, UpdateAccountCommand
from app.accounts.models import Account, AccountTypeEnum


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

    def get_account_by_id(self, account_id: uuid.UUID) -> Account | None:
        return self.db.execute(
            select(Account).where(Account.id == account_id)
        ).scalar_one_or_none()

    def update_account(
        self, account_id: uuid.UUID, account: UpdateAccountCommand
    ) -> Account:
        values: dict[str, str | bool] = {}
        if account.name is not None:
            values["name"] = account.name
        if account.type is not None:
            values["type"] = account.type
        if account.color is not None:
            values["color"] = account.color
        if account.icon is not None:
            values["icon"] = account.icon
        if account.is_active is not None:
            values["is_active"] = account.is_active

        return self.db.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(**values)
            .returning(Account)
        ).scalar_one()
