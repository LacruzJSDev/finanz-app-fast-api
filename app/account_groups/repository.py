import uuid
from dataclasses import dataclass
from datetime import datetime

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
    InvitationStatusEnum,
)
from app.shared.commands import UNSET


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
                # members viene completo, incluido quien consulta: es el único
                # sitio de esta respuesta donde viaja un role, así que
                # excluirse deja al cliente sin saber qué puede hacer en cada
                # grupo (account_groups.md §4).
                .options(selectinload(AccountGroup.members))
            )
            .scalars()
            .all()
        )
        return list(account_groups)

    def get_group_by_id(self, group_id: uuid.UUID) -> AccountGroup | None:
        return self.db.execute(
            select(AccountGroup).where(AccountGroup.id == group_id)
        ).scalar_one_or_none()

    def update_group(
        self, membership: AccountGroupMember, group: UpdateAccountGroupCommand
    ) -> AccountGroup:
        # La marca de ausencia es UNSET; un None que llega aquí es un null
        # explícito y sí se escribe (ARCHITECTURE.md §5.5). Un UPDATE parcial
        # no tiene forma fija de antemano, así que el dict no puede evitarse
        # aquí como sí se hace en create_account_group.
        values: dict[str, str | bool | None] = {}
        if group.name is not UNSET:
            values["name"] = group.name
        if group.color is not UNSET:
            values["color"] = group.color
        if group.icon is not UNSET:
            values["icon"] = group.icon
        if group.is_active is not UNSET:
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
        self, group_id: uuid.UUID, *, for_update: bool = False
    ) -> list[AccountGroupMember]:
        statement = (
            select(AccountGroupMember)
            .where(AccountGroupMember.group_id == group_id)
            .order_by(AccountGroupMember.id)
        )
        if for_update:
            statement = statement.with_for_update()

        account_group_members = self.db.execute(statement).scalars().all()
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

    def get_invitation_by_id(self, invitation_id: uuid.UUID) -> Invitation | None:
        invitation = self.db.execute(
            select(Invitation).where(Invitation.id == invitation_id)
        ).scalar_one_or_none()
        return invitation

    def get_invitations_by_group_id(self, group_id: uuid.UUID) -> list[Invitation]:
        invitations = (
            self.db.execute(
                select(Invitation)
                .where(Invitation.group_id == group_id)
                .order_by(Invitation.created_at.desc())
            )
            .scalars()
            .all()
        )
        return list(invitations)

    def get_invitation_by_code(self, code: str) -> Invitation | None:
        invitation = self.db.execute(
            select(Invitation).where(Invitation.code == code)
        ).scalar_one_or_none()
        return invitation

    def expire_invitation_by_id(
        self,
        invitation_id: uuid.UUID,
    ) -> Invitation:
        return self.db.execute(
            update(Invitation)
            .where(
                Invitation.id == invitation_id,
            )
            .values(status=InvitationStatusEnum.EXPIRED)
            .returning(Invitation)
        ).scalar_one()

    def delete_invitation_by_id(self, invitation_id: uuid.UUID) -> None:
        self.db.execute(delete(Invitation).where(Invitation.id == invitation_id))

    def accept_invitation_by_id(
        self,
        invitation_id: uuid.UUID,
        new_accepted_at: datetime,
        new_accepted_by: uuid.UUID,
    ) -> Invitation:
        return self.db.execute(
            update(Invitation)
            .where(
                Invitation.id == invitation_id,
            )
            .values(
                status=InvitationStatusEnum.ACCEPTED,
                accepted_at=new_accepted_at,
                accepted_by=new_accepted_by,
            )
            .returning(Invitation)
        ).scalar_one()
