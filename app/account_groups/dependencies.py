from typing import Annotated

from fastapi import Depends

from app.account_groups.repository import (
    AccountGroupMemberRepository,
    AccountGroupsRepository,
)
from app.account_groups.service import AccountGroupService
from app.shared.dependencies import DbSession
from app.users.dependencies import get_user_repository
from app.users.repository import UserRepository


def get_account_group_repository(db: DbSession) -> AccountGroupsRepository:
    return AccountGroupsRepository(db)


def get_account_group_member_repository(db: DbSession) -> AccountGroupMemberRepository:
    return AccountGroupMemberRepository(db)


def get_account_group_service(
    account_group_repo: Annotated[
        AccountGroupsRepository, Depends(get_account_group_repository)
    ],
    account_group_member_repo: Annotated[
        AccountGroupMemberRepository, Depends(get_account_group_member_repository)
    ],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> AccountGroupService:
    return AccountGroupService(account_group_repo, account_group_member_repo, user_repo)


AccountGroupServiceDep = Annotated[
    AccountGroupService, Depends(get_account_group_service)
]
