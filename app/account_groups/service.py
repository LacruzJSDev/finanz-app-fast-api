import uuid
from dataclasses import dataclass

from app.account_groups.commands import (
    AccountGroupCommand,
    AccountGroupMemberCommand,
    UpdateAccountGroupCommand,
)
from app.account_groups.models import (
    AccountGroup,
    AccountGroupMember,
    AccountGroupMemberRoleEnum,
)
from app.account_groups.repository import (
    AccountGroupMemberRepository,
    AccountGroupsRepository,
)
from app.account_groups.schemas import GroupMemberRead, GroupRead
from app.users.repository import UserRepository


@dataclass
class AccountGroupService:
    """Lógica de negocio del dominio account_groups."""

    account_group_repo: AccountGroupsRepository
    account_group_member_repo: AccountGroupMemberRepository
    user_repo: UserRepository

    def _to_group_read(self, group: AccountGroup) -> GroupRead:
        return GroupRead(
            id=group.id,
            name=group.name,
            color=group.color,
            icon=group.icon,
            is_active=group.is_active,
            created_at=group.created_at,
            updated_at=group.updated_at,
            members=[],
        )

    def create_group(self, user_id: uuid.UUID, group: AccountGroupCommand) -> GroupRead:
        group = self.account_group_repo.create_account_group(group)
        account_group_member_command = AccountGroupMemberCommand(
            group_id=group.id,
            user_id=user_id,
            role=AccountGroupMemberRoleEnum.OWNER,
        )

        self.account_group_member_repo.create_account_group_member(
            account_group_member_command
        )

        return self._to_group_read(group)

    def get_groups(self, user_id: uuid.UUID) -> list[GroupRead]:
        groups = self.account_group_repo.get_groups_by_user_id(user_id)
        user_ids = {member.user_id for group in groups for member in group.members}
        users = self.user_repo.get_users_by_ids(user_ids)
        users_by_id = {user.id: user for user in users}
        groups_read: list[GroupRead] = []
        for group in groups:
            group_read = self._to_group_read(group)
            group_read.members = [
                GroupMemberRead(
                    id=member.id,
                    user_id=member.user_id,
                    role=member.role,
                    name=users_by_id[member.user_id].name,
                    email=users_by_id[member.user_id].email,
                    created_at=member.created_at,
                    updated_at=member.updated_at,
                )
                for member in group.members
            ]
            groups_read.append(group_read)
        return groups_read

    def update_group(
        self, membership: AccountGroupMember, group: UpdateAccountGroupCommand
    ) -> GroupRead:
        group = self.account_group_repo.update_group(membership, group)
        return self._to_group_read(group)
