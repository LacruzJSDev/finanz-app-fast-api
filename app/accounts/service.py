import uuid
from dataclasses import dataclass

from app.accounts.commands import AccountCommand, UpdateAccountCommand
from app.accounts.repository import AccountRepository
from app.accounts.schemas import AccountRead
from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError


@dataclass
class AccountService:
    """Lógica de negocio del dominio account."""

    account_repo: AccountRepository

    def create_account(
        self, user_id: uuid.UUID, account_command: AccountCommand
    ) -> AccountRead:
        accounts_group = self.account_repo.get_accounts_by_group_id(
            account_command.group_id
        )
        # Solo las cuentas activas fijan la divisa del grupo (accounts.md §5) —
        # una archivada con una divisa antigua no debe bloquear cuentas nuevas.
        accounts_group_currency = {
            account.currency for account in accounts_group if account.is_active
        }
        if (
            len(accounts_group_currency) > 0
            and account_command.currency not in accounts_group_currency
        ):
            raise ConflictError(
                "La moneda no corresponde a las monedas usadas en el grupo de cuentas"
            )
        account = self.account_repo.create_account(user_id, account_command)
        account_read = AccountRead.model_validate(account)
        return account_read

    def get_accounts(self, group_id: uuid.UUID) -> list[AccountRead]:
        accounts = self.account_repo.get_accounts_by_group_id(group_id)
        accounts_read: list[AccountRead] = [
            AccountRead.model_validate(account) for account in accounts
        ]
        return accounts_read

    def get_account(self, account_id: uuid.UUID) -> AccountRead:
        account = self.account_repo.get_account_by_id(account_id)
        if account is None:
            raise NotFoundError("La cuenta no existe")
        account_read = AccountRead.model_validate(account)
        return account_read

    def update_account(
        self, account_id: uuid.UUID, account: UpdateAccountCommand
    ) -> AccountRead:
        fields = (
            account.name,
            account.type,
            account.color,
            account.icon,
            account.is_active,
        )
        if all(field is None for field in fields):
            raise BadRequestError("Debes incluir al menos un campo para actualizar")

        updated_account = self.account_repo.update_account(account_id, account)
        account_read = AccountRead.model_validate(updated_account)
        return account_read
