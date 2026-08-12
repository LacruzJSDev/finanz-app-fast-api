import uuid
from dataclasses import dataclass

from app.account_groups.commands import AccountGroupCommand, AccountGroupMemberCommand
from app.account_groups.models import AccountGroupMemberRoleEnum
from app.account_groups.repository import (
    AccountGroupMemberRepository,
    AccountGroupsRepository,
)
from app.account_groups.schemas import GroupMemberRead, GroupRead


@dataclass
class AccountGroupService:
    """Lógica de negocio del dominio account_groups."""

    account_group_repo: AccountGroupsRepository
    account_group_member_repo: AccountGroupMemberRepository

    def create_group(self, user_id: uuid.UUID, group: AccountGroupCommand) -> GroupRead:
        account_group = self.account_group_repo.create_account_group(group)
        account_group_member_command = AccountGroupMemberCommand(
            group_id=account_group.id,
            user_id=user_id,
            role=AccountGroupMemberRoleEnum.OWNER,
        )
        account_group_member = (
            self.account_group_member_repo.create_account_group_member(
                account_group_member_command
            )
        )

        group_read = GroupRead.model_validate(account_group)
        group_read.members = [GroupMemberRead.model_validate(account_group_member)]
        return group_read
