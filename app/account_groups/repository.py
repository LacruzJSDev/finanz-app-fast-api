import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.account_groups.commands import AccountGroupCommand, AccountGroupMemberCommand
from app.account_groups.models import AccountGroup, AccountGroupMember


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
