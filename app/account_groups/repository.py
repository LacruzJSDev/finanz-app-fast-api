import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from app.account_groups.commands import (
    AccountGroupCommand,
    AccountGroupMemberCommand,
    InvitationCommand,
    UpdateAccountGroupCommand,
)
from app.account_groups.models import (
    AccountGroup,
    AccountGroupMember,
    AccountGroupMemberRoleEnum,
    Invitation,
)


@dataclass
class AccountGroupsRepository:
    """Acceso a datos del dominio account_groups."""

    db: Session

    def create_account_group(self, group: AccountGroupCommand) -> AccountGroup:
        account_group = AccountGroup(
            name=group.name, color=group.color, icon=group.icon
        )
        self.db.add(account_group)
        self.db.flush()
        return account_group

    def get_groups_by_user_id(self, user_id: uuid.UUID) -> list[AccountGroup]:
        account_groups = (
            self.db.execute(
                select(AccountGroup)
                .join(AccountGroupMember)
                .where(AccountGroupMember.user_id == user_id)
                .options(
                    selectinload(
                        AccountGroup.members.and_(AccountGroupMember.user_id != user_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(account_groups)

    def update_group(
        self, membership: AccountGroupMember, group: UpdateAccountGroupCommand
    ) -> AccountGroup:
        # None aquí significa "no lo mandó el cliente" (ver UpdateGroupRequest /
        # router.py), no "bórralo" — así que solo se incluyen en el UPDATE las
        # columnas que sí llegaron. Un UPDATE parcial no tiene una forma fija
        # de antemano, así que el dict no puede evitarse aquí como sí se hace
        # en create_account_group.
        values: dict[str, str | bool] = {}
        if group.name is not None:
            values["name"] = group.name
        if group.color is not None:
            values["color"] = group.color
        if group.icon is not None:
            values["icon"] = group.icon
        if group.is_active is not None:
            values["is_active"] = group.is_active

        return self.db.execute(
            update(AccountGroup)
            .where(AccountGroup.id == membership.group_id)
            .values(**values)
            .returning(AccountGroup)
        ).scalar_one()


@dataclass
class AccountGroupMemberRepository:
    """Acceso a datos del dominio account_group_members."""

    db: Session

    def create_account_group_member(
        self, group_member: AccountGroupMemberCommand
    ) -> AccountGroupMember:
        account_group_member = AccountGroupMember(
            group_id=group_member.group_id,
            user_id=group_member.user_id,
            role=group_member.role,
        )
        self.db.add(account_group_member)
        self.db.flush()
        return account_group_member

    def get_membership(
        self, group_id: uuid.UUID, user_id: uuid.UUID
    ) -> AccountGroupMember | None:
        return self.db.execute(
            select(AccountGroupMember).where(
                AccountGroupMember.group_id == group_id,
                AccountGroupMember.user_id == user_id,
            )
        ).scalar_one_or_none()

    def get_group_members_by_group_id(
        self, group_id: uuid.UUID
    ) -> list[AccountGroupMember]:
        account_group_members = (
            self.db.execute(
                select(AccountGroupMember).where(
                    AccountGroupMember.group_id == group_id
                )
            )
            .scalars()
            .all()
        )
        return list(account_group_members)

    def change_group_member_role(
        self, group_id: uuid.UUID, user_id: uuid.UUID, role: AccountGroupMemberRoleEnum
    ) -> AccountGroupMember:
        return self.db.execute(
            update(AccountGroupMember)
            .where(
                AccountGroupMember.group_id == group_id,
                AccountGroupMember.user_id == user_id,
            )
            .values(role=role)
            .returning(AccountGroupMember)
        ).scalar_one()

    def delete_group_member(self, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self.db.execute(
            delete(AccountGroupMember).where(
                AccountGroupMember.group_id == group_id,
                AccountGroupMember.user_id == user_id,
            )
        )


@dataclass
class InvitationRepository:
    """Acceso a datos del dominio invitations."""

    db: Session

    def create_invitation(self, new_invitation: InvitationCommand) -> Invitation:
        invitation = Invitation(
            group_id=new_invitation.group_id,
            invited_by=new_invitation.invited_by,
            role=new_invitation.role,
            code=new_invitation.code,
            expires_at=new_invitation.expires_at,
        )
        self.db.add(invitation)
        self.db.flush()
        return invitation
