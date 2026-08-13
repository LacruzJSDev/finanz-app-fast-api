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
from app.shared.exceptions import BadRequestError, ConflictError, ForbiddenError
from app.users.models import User
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

    def _to_group_member_read(
        self, group_member: AccountGroupMember, user: User
    ) -> GroupMemberRead:
        return GroupMemberRead(
            id=group_member.id,
            user_id=group_member.user_id,
            role=group_member.role,
            name=user.name,
            email=user.email,
            created_at=group_member.created_at,
            updated_at=group_member.updated_at,
        )

    def create_group(self, user_id: uuid.UUID, group: AccountGroupCommand) -> GroupRead:
        account_group = self.account_group_repo.create_account_group(group)
        account_group_member_command = AccountGroupMemberCommand(
            group_id=account_group.id,
            user_id=user_id,
            role=AccountGroupMemberRoleEnum.OWNER,
        )

        self.account_group_member_repo.create_account_group_member(
            account_group_member_command
        )

        return self._to_group_read(account_group)

    def get_groups(self, user_id: uuid.UUID) -> list[GroupRead]:
        groups = self.account_group_repo.get_groups_by_user_id(user_id)
        user_ids = {member.user_id for group in groups for member in group.members}
        users = self.user_repo.get_users_by_ids(user_ids)
        users_by_id = {user.id: user for user in users}
        groups_read: list[GroupRead] = []
        for group in groups:
            group_read = self._to_group_read(group)
            group_read.members = [
                self._to_group_member_read(member, users_by_id[member.user_id])
                for member in group.members
            ]
            groups_read.append(group_read)
        return groups_read

    def update_group(
        self, membership: AccountGroupMember, group: UpdateAccountGroupCommand
    ) -> GroupRead:
        fields = (group.name, group.color, group.icon, group.is_active)
        if all(field is None for field in fields):
            raise BadRequestError("Debes incluir al menos un campo para actualizar")

        account_group = self.account_group_repo.update_group(membership, group)
        return self._to_group_read(account_group)

    def get_group_members(self, group_id: uuid.UUID) -> list[GroupMemberRead]:
        members = self.account_group_member_repo.get_group_members_by_group_id(group_id)
        user_ids = {member.user_id for member in members}
        users = self.user_repo.get_users_by_ids(user_ids)
        users_by_id = {user.id: user for user in users}
        members_read: list[GroupMemberRead] = []
        for member in members:
            member_read = self._to_group_member_read(
                member, users_by_id[member.user_id]
            )
            members_read.append(member_read)

        return members_read

    def change_group_member_role(
        self, group_id: uuid.UUID, user_id: uuid.UUID, role: AccountGroupMemberRoleEnum
    ) -> GroupMemberRead:
        members = self.get_group_members(group_id)
        members_roles = {member.role for member in members if member.user_id != user_id}
        members_roles.add(role)
        if AccountGroupMemberRoleEnum.OWNER not in members_roles:
            raise ConflictError("No pueden eliminarse todos los propietarios")
        member = self.account_group_member_repo.change_group_member_role(
            group_id, user_id, role
        )
        user = self.user_repo.get_user_by_id(member.user_id)
        if user is None:
            raise ConflictError("El miembro del grupo no existe")
        member_read = self._to_group_member_read(member, user)
        return member_read

    def expel_group_member(
        self,
        group_id: uuid.UUID,
        expeled_user_id: uuid.UUID,
        request_user_id: uuid.UUID,
    ) -> None:
        members = self.get_group_members(group_id)
        members_by_user_id = {member.user_id: member for member in members}

        remaining_roles = {
            member.role for member in members if member.user_id != expeled_user_id
        }
        if AccountGroupMemberRoleEnum.OWNER not in remaining_roles:
            raise ConflictError("No pueden eliminarse todos los propietarios")

        is_self_removal = request_user_id == expeled_user_id
        if not is_self_removal:
            requester_role = members_by_user_id[request_user_id].role
            target_role = members_by_user_id[expeled_user_id].role

            if requester_role == AccountGroupMemberRoleEnum.MEMBER:
                raise ForbiddenError("No tienes permiso para expulsar miembros")
            if (
                requester_role == AccountGroupMemberRoleEnum.ADMIN
                and target_role == AccountGroupMemberRoleEnum.OWNER
            ):
                raise ForbiddenError(
                    "Un administrador no puede expulsar a un propietario"
                )

        self.account_group_member_repo.delete_group_member(group_id, expeled_user_id)
