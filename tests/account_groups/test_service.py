import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.account_groups.commands import (
    AccountGroupCommand,
    UpdateAccountGroupCommand,
)
from app.account_groups.models import (
    AccountGroup,
    AccountGroupMember,
    AccountGroupMemberRoleEnum,
    Invitation,
    InvitationStatusEnum,
)
from app.account_groups.repository import (
    AccountGroupMemberRepository,
    AccountGroupsRepository,
    InvitationRepository,
)
from app.account_groups.service import AccountGroupService
from app.shared.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.users.models import User
from app.users.repository import UserRepository


def make_group(**overrides: object) -> AccountGroup:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "Test Group",
        "color": None,
        "icon": None,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return AccountGroup(**defaults)  # pyright: ignore[reportArgumentType]


def make_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    role: AccountGroupMemberRoleEnum = AccountGroupMemberRoleEnum.MEMBER,
    **overrides: object,
) -> AccountGroupMember:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "group_id": group_id,
        "user_id": user_id,
        "role": role,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return AccountGroupMember(**defaults)  # pyright: ignore[reportArgumentType]


def make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "email": "user@test.com",
        "name": "Test User",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return User(**defaults)  # pyright: ignore[reportArgumentType]


def make_invitation(**overrides: object) -> Invitation:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "group_id": uuid.uuid4(),
        "invited_by": uuid.uuid4(),
        "role": AccountGroupMemberRoleEnum.MEMBER,
        "code": "test-code",
        "status": InvitationStatusEnum.PENDING,
        "accepted_by": None,
        "accepted_at": None,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Invitation(**defaults)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def account_group_repo() -> MagicMock:
    return MagicMock(spec=AccountGroupsRepository)


@pytest.fixture
def member_repo() -> MagicMock:
    return MagicMock(spec=AccountGroupMemberRepository)


def _users_for_ids(ids: set[uuid.UUID]) -> list[User]:
    return [make_user(id=user_id) for user_id in ids]


@pytest.fixture
def user_repo() -> MagicMock:
    repo = MagicMock(spec=UserRepository)
    # get_group_members (usado internamente por change_group_member_role y
    # expel_group_member) siempre resuelve los usuarios de los miembros que
    # acaba de leer — por defecto, uno por cada id pedido, para no tener que
    # configurarlo en cada test que no le interesa el contenido de User.
    repo.get_users_by_ids.side_effect = _users_for_ids
    return repo


@pytest.fixture
def invitation_repo() -> MagicMock:
    return MagicMock(spec=InvitationRepository)


@pytest.fixture
def service(
    account_group_repo: MagicMock,
    member_repo: MagicMock,
    user_repo: MagicMock,
    invitation_repo: MagicMock,
) -> AccountGroupService:
    return AccountGroupService(
        account_group_repo, member_repo, user_repo, invitation_repo
    )


class TestCreateGroup:
    def test_creates_group_and_owner_membership(
        self,
        service: AccountGroupService,
        account_group_repo: MagicMock,
        member_repo: MagicMock,
    ):
        user_id = uuid.uuid4()
        group = make_group()
        account_group_repo.create_account_group.return_value = group

        result = service.create_group(
            user_id, AccountGroupCommand(name="New Group", color=None, icon=None)
        )

        assert result.id == group.id
        member_repo.create_account_group_member.assert_called_once()
        command = member_repo.create_account_group_member.call_args.args[0]
        assert command.group_id == group.id
        assert command.user_id == user_id
        assert command.role == AccountGroupMemberRoleEnum.OWNER


class TestUpdateGroup:
    def test_raises_bad_request_when_no_fields(self, service: AccountGroupService):
        membership = make_member(uuid.uuid4(), uuid.uuid4())
        command = UpdateAccountGroupCommand(
            name=None, color=None, icon=None, is_active=None
        )

        with pytest.raises(BadRequestError):
            service.update_group(membership, command)

    def test_updates_when_at_least_one_field(
        self, service: AccountGroupService, account_group_repo: MagicMock
    ):
        membership = make_member(uuid.uuid4(), uuid.uuid4())
        updated = make_group(name="Renamed")
        account_group_repo.update_group.return_value = updated
        command = UpdateAccountGroupCommand(
            name="Renamed", color=None, icon=None, is_active=None
        )

        result = service.update_group(membership, command)

        assert result.name == "Renamed"


class TestChangeGroupMemberRole:
    def test_raises_conflict_when_demoting_sole_owner(
        self, service: AccountGroupService, member_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        owner = make_member(group_id, owner_id, AccountGroupMemberRoleEnum.OWNER)
        member_repo.get_group_members_by_group_id.return_value = [owner]

        with pytest.raises(ConflictError):
            service.change_group_member_role(
                group_id, owner_id, AccountGroupMemberRoleEnum.ADMIN
            )

        member_repo.change_group_member_role.assert_not_called()

    def test_allows_demoting_owner_when_another_owner_remains(
        self,
        service: AccountGroupService,
        member_repo: MagicMock,
        user_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        owner_a_id = uuid.uuid4()
        owner_b_id = uuid.uuid4()
        owner_a = make_member(group_id, owner_a_id, AccountGroupMemberRoleEnum.OWNER)
        owner_b = make_member(group_id, owner_b_id, AccountGroupMemberRoleEnum.OWNER)
        member_repo.get_group_members_by_group_id.return_value = [owner_a, owner_b]
        demoted = make_member(group_id, owner_a_id, AccountGroupMemberRoleEnum.ADMIN)
        member_repo.change_group_member_role.return_value = demoted
        user_repo.get_user_by_id.return_value = make_user(id=owner_a_id)

        result = service.change_group_member_role(
            group_id, owner_a_id, AccountGroupMemberRoleEnum.ADMIN
        )

        assert result.role == AccountGroupMemberRoleEnum.ADMIN

    def test_raises_conflict_when_target_user_missing(
        self,
        service: AccountGroupService,
        member_repo: MagicMock,
        user_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        member_id = uuid.uuid4()
        owner = make_member(group_id, owner_id, AccountGroupMemberRoleEnum.OWNER)
        member = make_member(group_id, member_id, AccountGroupMemberRoleEnum.MEMBER)
        member_repo.get_group_members_by_group_id.return_value = [owner, member]
        member_repo.change_group_member_role.return_value = make_member(
            group_id, member_id, AccountGroupMemberRoleEnum.ADMIN
        )
        user_repo.get_user_by_id.return_value = None

        with pytest.raises(ConflictError):
            service.change_group_member_role(
                group_id, member_id, AccountGroupMemberRoleEnum.ADMIN
            )


class TestExpelGroupMember:
    def test_raises_conflict_when_expelling_sole_owner(
        self, service: AccountGroupService, member_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        owner = make_member(group_id, owner_id, AccountGroupMemberRoleEnum.OWNER)
        member_repo.get_group_members_by_group_id.return_value = [owner]

        with pytest.raises(ConflictError):
            service.expel_group_member(group_id, owner_id, owner_id)

        member_repo.delete_group_member.assert_not_called()

    def test_member_cannot_expel_another_member(
        self, service: AccountGroupService, member_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        member_a_id = uuid.uuid4()
        member_b_id = uuid.uuid4()
        owner = make_member(group_id, owner_id, AccountGroupMemberRoleEnum.OWNER)
        member_a = make_member(group_id, member_a_id, AccountGroupMemberRoleEnum.MEMBER)
        member_b = make_member(group_id, member_b_id, AccountGroupMemberRoleEnum.MEMBER)
        member_repo.get_group_members_by_group_id.return_value = [
            owner,
            member_a,
            member_b,
        ]

        with pytest.raises(ForbiddenError):
            service.expel_group_member(group_id, member_b_id, member_a_id)

        member_repo.delete_group_member.assert_not_called()

    def test_admin_cannot_expel_owner(
        self, service: AccountGroupService, member_repo: MagicMock
    ):
        # Dos owners: expulsar a uno de los dos no deja el grupo sin
        # propietario, así que la comprobación que falla de verdad aquí es
        # el rol del solicitante, no la de owner único.
        group_id = uuid.uuid4()
        owner_a_id = uuid.uuid4()
        owner_b_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        owner_a = make_member(group_id, owner_a_id, AccountGroupMemberRoleEnum.OWNER)
        owner_b = make_member(group_id, owner_b_id, AccountGroupMemberRoleEnum.OWNER)
        admin = make_member(group_id, admin_id, AccountGroupMemberRoleEnum.ADMIN)
        member_repo.get_group_members_by_group_id.return_value = [
            owner_a,
            owner_b,
            admin,
        ]

        with pytest.raises(ForbiddenError):
            service.expel_group_member(group_id, owner_a_id, admin_id)

        member_repo.delete_group_member.assert_not_called()

    def test_admin_can_expel_member(
        self, service: AccountGroupService, member_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        member_id = uuid.uuid4()
        owner = make_member(group_id, owner_id, AccountGroupMemberRoleEnum.OWNER)
        admin = make_member(group_id, admin_id, AccountGroupMemberRoleEnum.ADMIN)
        member = make_member(group_id, member_id, AccountGroupMemberRoleEnum.MEMBER)
        member_repo.get_group_members_by_group_id.return_value = [
            owner,
            admin,
            member,
        ]

        service.expel_group_member(group_id, member_id, admin_id)

        member_repo.delete_group_member.assert_called_once_with(group_id, member_id)

    def test_member_can_remove_self(
        self, service: AccountGroupService, member_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        member_id = uuid.uuid4()
        owner = make_member(group_id, owner_id, AccountGroupMemberRoleEnum.OWNER)
        member = make_member(group_id, member_id, AccountGroupMemberRoleEnum.MEMBER)
        member_repo.get_group_members_by_group_id.return_value = [owner, member]

        service.expel_group_member(group_id, member_id, member_id)

        member_repo.delete_group_member.assert_called_once_with(group_id, member_id)


class TestCreateInvitation:
    def test_raises_conflict_when_inviter_missing(
        self,
        service: AccountGroupService,
        invitation_repo: MagicMock,
        user_repo: MagicMock,
    ):
        invitation_repo.create_invitation.return_value = make_invitation(
            invited_by=None
        )

        with pytest.raises(ConflictError):
            service.create_invitation(
                uuid.uuid4(), uuid.uuid4(), AccountGroupMemberRoleEnum.MEMBER
            )

    def test_creates_invitation_with_seven_day_expiry(
        self,
        service: AccountGroupService,
        invitation_repo: MagicMock,
        user_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        inviter_id = uuid.uuid4()
        invitation = make_invitation(group_id=group_id, invited_by=inviter_id)
        invitation_repo.create_invitation.return_value = invitation
        user_repo.get_user_by_id.return_value = make_user(id=inviter_id)

        before = datetime.now(timezone.utc)
        result = service.create_invitation(
            group_id, inviter_id, AccountGroupMemberRoleEnum.ADMIN
        )

        command = invitation_repo.create_invitation.call_args.args[0]
        assert command.group_id == group_id
        assert command.invited_by == inviter_id
        assert command.role == AccountGroupMemberRoleEnum.ADMIN
        assert command.expires_at - before >= timedelta(days=7)
        assert command.expires_at - before < timedelta(days=7, minutes=1)
        assert result.invited_by is not None
        assert result.invited_by.email == "user@test.com"


class TestGetInvitation:
    def test_raises_not_found_when_missing(
        self, service: AccountGroupService, invitation_repo: MagicMock
    ):
        invitation_repo.get_invitation_by_code.return_value = None

        with pytest.raises(NotFoundError):
            service.get_invitation("missing-code")

    def test_lazily_expires_when_past_expiry(
        self,
        service: AccountGroupService,
        invitation_repo: MagicMock,
        user_repo: MagicMock,
    ):
        invitation = make_invitation(
            expires_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
        invitation_repo.get_invitation_by_code.return_value = invitation
        invitation_repo.expire_invitation_by_id.return_value = make_invitation(
            id=invitation.id, status=InvitationStatusEnum.EXPIRED
        )

        result = service.get_invitation("expired-code")

        assert result.status == InvitationStatusEnum.EXPIRED
        invitation_repo.expire_invitation_by_id.assert_called_once_with(invitation.id)
        user_repo.get_user_by_id.assert_not_called()

    def test_lazily_expires_when_inviter_deleted(
        self,
        service: AccountGroupService,
        invitation_repo: MagicMock,
    ):
        invitation = make_invitation(invited_by=None)
        invitation_repo.get_invitation_by_code.return_value = invitation
        invitation_repo.expire_invitation_by_id.return_value = make_invitation(
            id=invitation.id, invited_by=None, status=InvitationStatusEnum.EXPIRED
        )

        result = service.get_invitation("orphaned-code")

        assert result.status == InvitationStatusEnum.EXPIRED
        assert result.invited_by is None

    def test_returns_pending_invitation_unchanged(
        self,
        service: AccountGroupService,
        invitation_repo: MagicMock,
        user_repo: MagicMock,
    ):
        inviter_id = uuid.uuid4()
        invitation = make_invitation(invited_by=inviter_id)
        invitation_repo.get_invitation_by_code.return_value = invitation
        user_repo.get_user_by_id.return_value = make_user(id=inviter_id)

        result = service.get_invitation(invitation.code)

        assert result.status == InvitationStatusEnum.PENDING
        invitation_repo.expire_invitation_by_id.assert_not_called()


class TestAcceptInvitation:
    def test_raises_conflict_when_already_a_member(
        self, service: AccountGroupService, member_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        user_id = uuid.uuid4()
        member_repo.get_group_members_by_group_id.return_value = [
            make_member(group_id, user_id)
        ]

        with pytest.raises(ConflictError):
            service.accept_invitation(group_id, user_id, uuid.uuid4())

    def test_raises_not_found_when_invitation_missing(
        self,
        service: AccountGroupService,
        member_repo: MagicMock,
        invitation_repo: MagicMock,
    ):
        member_repo.get_group_members_by_group_id.return_value = []
        invitation_repo.get_invitation_by_id.return_value = None

        with pytest.raises(NotFoundError):
            service.accept_invitation(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    def test_raises_not_found_when_invitation_belongs_to_other_group(
        self,
        service: AccountGroupService,
        member_repo: MagicMock,
        invitation_repo: MagicMock,
    ):
        member_repo.get_group_members_by_group_id.return_value = []
        invitation_repo.get_invitation_by_id.return_value = make_invitation(
            group_id=uuid.uuid4()
        )

        with pytest.raises(NotFoundError):
            service.accept_invitation(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    def test_raises_conflict_and_expires_when_expired_but_still_pending(
        self,
        service: AccountGroupService,
        member_repo: MagicMock,
        invitation_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        invitation = make_invitation(
            group_id=group_id,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            status=InvitationStatusEnum.PENDING,
        )
        member_repo.get_group_members_by_group_id.return_value = []
        invitation_repo.get_invitation_by_id.return_value = invitation

        with pytest.raises(ConflictError):
            service.accept_invitation(group_id, uuid.uuid4(), invitation.id)

        invitation_repo.expire_invitation_by_id.assert_called_once_with(invitation.id)

    def test_raises_conflict_when_already_expired_does_not_expire_twice(
        self,
        service: AccountGroupService,
        member_repo: MagicMock,
        invitation_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        invitation = make_invitation(
            group_id=group_id, status=InvitationStatusEnum.EXPIRED
        )
        member_repo.get_group_members_by_group_id.return_value = []
        invitation_repo.get_invitation_by_id.return_value = invitation

        with pytest.raises(ConflictError):
            service.accept_invitation(group_id, uuid.uuid4(), invitation.id)

        invitation_repo.expire_invitation_by_id.assert_not_called()

    def test_raises_conflict_when_already_accepted(
        self,
        service: AccountGroupService,
        member_repo: MagicMock,
        invitation_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        invitation = make_invitation(
            group_id=group_id, status=InvitationStatusEnum.ACCEPTED
        )
        member_repo.get_group_members_by_group_id.return_value = []
        invitation_repo.get_invitation_by_id.return_value = invitation

        with pytest.raises(ConflictError):
            service.accept_invitation(group_id, uuid.uuid4(), invitation.id)

    def test_accepts_and_creates_membership_on_success(
        self,
        service: AccountGroupService,
        member_repo: MagicMock,
        invitation_repo: MagicMock,
        user_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        user_id = uuid.uuid4()
        inviter_id = uuid.uuid4()
        invitation = make_invitation(
            group_id=group_id,
            invited_by=inviter_id,
            role=AccountGroupMemberRoleEnum.ADMIN,
        )
        member_repo.get_group_members_by_group_id.return_value = []
        invitation_repo.get_invitation_by_id.return_value = invitation
        invitation_repo.accept_invitation_by_id.return_value = make_invitation(
            id=invitation.id,
            group_id=group_id,
            invited_by=inviter_id,
            status=InvitationStatusEnum.ACCEPTED,
        )
        user_repo.get_user_by_id.return_value = make_user(id=inviter_id)

        result = service.accept_invitation(group_id, user_id, invitation.id)

        assert result.status == InvitationStatusEnum.ACCEPTED
        member_repo.create_account_group_member.assert_called_once()
        command = member_repo.create_account_group_member.call_args.args[0]
        assert command.group_id == group_id
        assert command.user_id == user_id
        assert command.role == AccountGroupMemberRoleEnum.ADMIN
