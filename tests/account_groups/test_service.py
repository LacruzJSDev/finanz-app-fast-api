import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

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
from app.account_groups.schemas import PendingFixedExpenseRead, UpdateGroupRequest
from app.account_groups.service import (
    AccountGroupService,
    GroupOverviewService,
    build_projection,
    daily_safe_spend,
    pending_fixed_expenses,
)
from app.accounts.schemas import GroupBalanceRead
from app.accounts.service import AccountService
from app.payment_plans.models import FrequencyUnitEnum
from app.payment_plans.schemas import PaymentPlanRead
from app.payment_plans.service import PaymentPlanService
from app.shared.commands import UNSET
from app.shared.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.transactions.models import TransactionTypeEnum
from app.transactions.schemas import DailySpendRead
from app.transactions.service import TransactionService
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


def make_payment_plan(**overrides: object) -> PaymentPlanRead:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "to_account_id": None,
        "category_id": None,
        "type": TransactionTypeEnum.EXPENSE,
        "amount": 10_000,
        "description": "Alquiler",
        "next_due_date": date(2026, 3, 1),
        "end_date": None,
        "is_recurring": True,
        "is_active": True,
        "frequency_interval": 1,
        "frequency_unit": FrequencyUnitEnum.MONTH,
        "created_by": None,
        "updated_by": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return PaymentPlanRead(**defaults)  # pyright: ignore[reportArgumentType]


def make_pending_expense(**overrides: object) -> PendingFixedExpenseRead:
    defaults: dict[str, object] = {
        "payment_plan_id": uuid.uuid4(),
        "description": "Alquiler",
        "amount": 10_000,
        "due_date": date(2026, 3, 1),
    }
    defaults.update(overrides)
    return PendingFixedExpenseRead(**defaults)  # pyright: ignore[reportArgumentType]


def make_group_balance(**overrides: object) -> GroupBalanceRead:
    defaults: dict[str, object] = {
        "net_worth": 500_000,
        "available": 100_000,
        "account_count": 3,
        "spendable_account_count": 2,
        "currency": "EUR",
    }
    defaults.update(overrides)
    return GroupBalanceRead(**defaults)  # pyright: ignore[reportArgumentType]


def make_daily_spend(**overrides: object) -> DailySpendRead:
    defaults: dict[str, object] = {
        "date": date(2026, 3, 1),
        "spent": 2_500,
        "transaction_count": 2,
    }
    defaults.update(overrides)
    return DailySpendRead(**defaults)  # pyright: ignore[reportArgumentType]


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


@pytest.fixture
def account_service() -> MagicMock:
    return MagicMock(spec=AccountService)


@pytest.fixture
def payment_plan_service() -> MagicMock:
    return MagicMock(spec=PaymentPlanService)


@pytest.fixture
def transaction_service() -> MagicMock:
    return MagicMock(spec=TransactionService)


@pytest.fixture
def overview_service(
    account_service: MagicMock,
    payment_plan_service: MagicMock,
    transaction_service: MagicMock,
) -> GroupOverviewService:
    return GroupOverviewService(
        account_service, payment_plan_service, transaction_service
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


class TestGetGroups:
    def test_includes_the_requesting_user_among_the_members(
        self,
        service: AccountGroupService,
        account_group_repo: MagicMock,
        user_repo: MagicMock,
    ):
        # account_groups.md §4: members es el único sitio de esta respuesta
        # donde viaja un role, así que excluirse dejaría al cliente sin saber
        # qué puede hacer en el grupo.
        requester = make_user(name="Yo")
        other = make_user(name="Otro")
        group = make_group()
        group.members = [
            make_member(group.id, requester.id, AccountGroupMemberRoleEnum.OWNER),
            make_member(group.id, other.id, AccountGroupMemberRoleEnum.MEMBER),
        ]
        account_group_repo.get_groups_by_user_id.return_value = [group]
        user_repo.get_users_by_ids.side_effect = None
        user_repo.get_users_by_ids.return_value = [requester, other]

        result = service.get_groups(requester.id)

        member_ids = {member.user_id for member in result[0].members}
        assert requester.id in member_ids
        assert member_ids == {requester.id, other.id}

    def test_exposes_the_role_of_the_requesting_user(
        self,
        service: AccountGroupService,
        account_group_repo: MagicMock,
        user_repo: MagicMock,
    ):
        requester = make_user()
        group = make_group()
        group.members = [
            make_member(group.id, requester.id, AccountGroupMemberRoleEnum.ADMIN)
        ]
        account_group_repo.get_groups_by_user_id.return_value = [group]
        user_repo.get_users_by_ids.side_effect = None
        user_repo.get_users_by_ids.return_value = [requester]

        result = service.get_groups(requester.id)

        own = next(m for m in result[0].members if m.user_id == requester.id)
        assert own.role == AccountGroupMemberRoleEnum.ADMIN

    def test_returns_a_group_without_dropping_any_member(
        self,
        service: AccountGroupService,
        account_group_repo: MagicMock,
        user_repo: MagicMock,
    ):
        requester = make_user()
        others = [make_user(), make_user()]
        group = make_group()
        group.members = [
            make_member(group.id, user.id) for user in [requester, *others]
        ]
        account_group_repo.get_groups_by_user_id.return_value = [group]
        user_repo.get_users_by_ids.side_effect = None
        user_repo.get_users_by_ids.return_value = [requester, *others]

        result = service.get_groups(requester.id)

        # Un recuento derivado de members saldría corto si se filtrara a nadie.
        assert len(result[0].members) == 3

    def test_returns_empty_when_the_user_has_no_groups(
        self, service: AccountGroupService, account_group_repo: MagicMock
    ):
        account_group_repo.get_groups_by_user_id.return_value = []

        assert service.get_groups(uuid.uuid4()) == []


class TestUpdateGroup:
    def test_raises_bad_request_when_no_fields(self, service: AccountGroupService):
        membership = make_member(uuid.uuid4(), uuid.uuid4())
        command = UpdateAccountGroupCommand()

        with pytest.raises(BadRequestError):
            service.update_group(membership, command)

    def test_updates_when_at_least_one_field(
        self, service: AccountGroupService, account_group_repo: MagicMock
    ):
        membership = make_member(uuid.uuid4(), uuid.uuid4())
        updated = make_group(name="Renamed")
        account_group_repo.update_group.return_value = updated
        command = UpdateAccountGroupCommand(name="Renamed")

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
        account_group_repo: MagicMock,
    ):
        inviter = make_user(name="Ana")
        invitation = make_invitation(
            invited_by=inviter.id,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        invitation_repo.get_invitation_by_code.return_value = invitation
        invitation_repo.expire_invitation_by_id.return_value = make_invitation(
            id=invitation.id,
            invited_by=inviter.id,
            status=InvitationStatusEnum.EXPIRED,
        )
        user_repo.get_user_by_id.return_value = inviter
        account_group_repo.get_group_by_id.return_value = make_group()

        result = service.get_invitation("expired-code")

        assert result.status == InvitationStatusEnum.EXPIRED
        invitation_repo.expire_invitation_by_id.assert_called_once_with(invitation.id)
        # account_groups.md §4: caducar no oculta quién invitó — solo lo oculta
        # que esa persona haya borrado su cuenta.
        assert result.invited_by is not None
        assert result.invited_by.name == "Ana"

    def test_lazily_expires_when_inviter_deleted(
        self,
        service: AccountGroupService,
        invitation_repo: MagicMock,
        account_group_repo: MagicMock,
    ):
        invitation = make_invitation(invited_by=None)
        invitation_repo.get_invitation_by_code.return_value = invitation
        invitation_repo.expire_invitation_by_id.return_value = make_invitation(
            id=invitation.id, invited_by=None, status=InvitationStatusEnum.EXPIRED
        )
        account_group_repo.get_group_by_id.return_value = make_group()

        result = service.get_invitation("orphaned-code")

        assert result.status == InvitationStatusEnum.EXPIRED
        assert result.invited_by is None

    def test_returns_pending_invitation_unchanged(
        self,
        service: AccountGroupService,
        invitation_repo: MagicMock,
        user_repo: MagicMock,
        account_group_repo: MagicMock,
    ):
        inviter_id = uuid.uuid4()
        invitation = make_invitation(invited_by=inviter_id)
        invitation_repo.get_invitation_by_code.return_value = invitation
        user_repo.get_user_by_id.return_value = make_user(id=inviter_id)
        account_group_repo.get_group_by_id.return_value = make_group()

        result = service.get_invitation(invitation.code)

        assert result.status == InvitationStatusEnum.PENDING
        invitation_repo.expire_invitation_by_id.assert_not_called()

    def test_leaves_an_accepted_invitation_untouched(
        self,
        service: AccountGroupService,
        invitation_repo: MagicMock,
        user_repo: MagicMock,
        account_group_repo: MagicMock,
    ):
        # Una aceptada cuyo plazo ya pasó conserva su status: la caducidad
        # perezosa solo alcanza a las pending (account_groups.md §5).
        inviter_id = uuid.uuid4()
        invitation = make_invitation(
            invited_by=inviter_id,
            status=InvitationStatusEnum.ACCEPTED,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        invitation_repo.get_invitation_by_code.return_value = invitation
        user_repo.get_user_by_id.return_value = make_user(id=inviter_id)
        account_group_repo.get_group_by_id.return_value = make_group()

        result = service.get_invitation(invitation.code)

        assert result.status == InvitationStatusEnum.ACCEPTED
        invitation_repo.expire_invitation_by_id.assert_not_called()

    def test_embeds_the_full_group(
        self,
        service: AccountGroupService,
        invitation_repo: MagicMock,
        user_repo: MagicMock,
        account_group_repo: MagicMock,
    ):
        inviter_id = uuid.uuid4()
        group = make_group(name="Piso compartido", color="#fff", icon="home")
        invitation = make_invitation(group_id=group.id, invited_by=inviter_id)
        invitation_repo.get_invitation_by_code.return_value = invitation
        user_repo.get_user_by_id.return_value = make_user(id=inviter_id)
        account_group_repo.get_group_by_id.return_value = group

        result = service.get_invitation(invitation.code)

        assert account_group_repo.get_group_by_id.call_args.args[0] == group.id
        assert result.group.id == group.id
        assert result.group.name == "Piso compartido"
        assert result.group.color == "#fff"
        assert result.group.icon == "home"


def _expired_copy(invitation_id: uuid.UUID) -> Invitation:
    return make_invitation(id=invitation_id, status=InvitationStatusEnum.EXPIRED)


class TestGetGroupInvitations:
    def test_returns_every_invitation_with_its_code(
        self, service: AccountGroupService, invitation_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        pending = make_invitation(group_id=group_id, code="pending-code")
        accepted = make_invitation(
            group_id=group_id,
            code="accepted-code",
            status=InvitationStatusEnum.ACCEPTED,
        )
        invitation_repo.get_invitations_by_group_id.return_value = [accepted, pending]

        result = service.get_group_invitations(group_id)

        assert invitation_repo.get_invitations_by_group_id.call_args.args[0] == group_id
        assert [invitation.code for invitation in result] == [
            "accepted-code",
            "pending-code",
        ]
        assert [invitation.status for invitation in result] == [
            InvitationStatusEnum.ACCEPTED,
            InvitationStatusEnum.PENDING,
        ]

    def test_expires_a_pending_past_expiry_and_leaves_the_valid_one(
        self, service: AccountGroupService, invitation_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        stale = make_invitation(
            group_id=group_id,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        fresh = make_invitation(group_id=group_id)
        invitation_repo.get_invitations_by_group_id.return_value = [stale, fresh]
        invitation_repo.expire_invitation_by_id.side_effect = _expired_copy

        result = service.get_group_invitations(group_id)

        assert [invitation.status for invitation in result] == [
            InvitationStatusEnum.EXPIRED,
            InvitationStatusEnum.PENDING,
        ]
        invitation_repo.expire_invitation_by_id.assert_called_once_with(stale.id)

    def test_expires_a_pending_whose_inviter_was_deleted(
        self, service: AccountGroupService, invitation_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        orphaned = make_invitation(group_id=group_id, invited_by=None)
        invitation_repo.get_invitations_by_group_id.return_value = [orphaned]
        invitation_repo.expire_invitation_by_id.side_effect = _expired_copy

        result = service.get_group_invitations(group_id)

        assert result[0].status == InvitationStatusEnum.EXPIRED
        invitation_repo.expire_invitation_by_id.assert_called_once_with(orphaned.id)

    def test_does_not_expire_an_accepted_invitation(
        self, service: AccountGroupService, invitation_repo: MagicMock
    ):
        # Su fila es el registro de que alguien entró al grupo, aunque su
        # plazo haya pasado (account_groups.md §5).
        group_id = uuid.uuid4()
        accepted = make_invitation(
            group_id=group_id,
            status=InvitationStatusEnum.ACCEPTED,
            expires_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        invitation_repo.get_invitations_by_group_id.return_value = [accepted]

        result = service.get_group_invitations(group_id)

        assert result[0].status == InvitationStatusEnum.ACCEPTED
        invitation_repo.expire_invitation_by_id.assert_not_called()

    def test_resolves_the_inviter_of_each_invitation(
        self,
        service: AccountGroupService,
        invitation_repo: MagicMock,
        user_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        inviter_id = uuid.uuid4()
        invitation = make_invitation(group_id=group_id, invited_by=inviter_id)
        invitation_repo.get_invitations_by_group_id.return_value = [invitation]
        user_repo.get_users_by_ids.side_effect = None
        user_repo.get_users_by_ids.return_value = [
            make_user(id=inviter_id, name="Ana", email="ana@test.com")
        ]

        result = service.get_group_invitations(group_id)

        assert user_repo.get_users_by_ids.call_args.args[0] == {inviter_id}
        assert result[0].invited_by is not None
        assert result[0].invited_by.name == "Ana"


class TestRevokeInvitation:
    def test_raises_conflict_when_accepted(
        self, service: AccountGroupService, invitation_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        invitation = make_invitation(
            group_id=group_id, status=InvitationStatusEnum.ACCEPTED
        )
        invitation_repo.get_invitation_by_id.return_value = invitation

        with pytest.raises(ConflictError):
            service.revoke_invitation(group_id, invitation.id)

        invitation_repo.delete_invitation_by_id.assert_not_called()

    def test_deletes_a_pending_invitation(
        self, service: AccountGroupService, invitation_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        invitation = make_invitation(group_id=group_id)
        invitation_repo.get_invitation_by_id.return_value = invitation

        service.revoke_invitation(group_id, invitation.id)

        invitation_repo.delete_invitation_by_id.assert_called_once_with(invitation.id)

    def test_deletes_an_expired_invitation(
        self, service: AccountGroupService, invitation_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        invitation = make_invitation(
            group_id=group_id, status=InvitationStatusEnum.EXPIRED
        )
        invitation_repo.get_invitation_by_id.return_value = invitation

        service.revoke_invitation(group_id, invitation.id)

        invitation_repo.delete_invitation_by_id.assert_called_once_with(invitation.id)

    def test_raises_not_found_when_missing(
        self, service: AccountGroupService, invitation_repo: MagicMock
    ):
        invitation_repo.get_invitation_by_id.return_value = None

        with pytest.raises(NotFoundError):
            service.revoke_invitation(uuid.uuid4(), uuid.uuid4())

        invitation_repo.delete_invitation_by_id.assert_not_called()

    def test_raises_not_found_when_invitation_belongs_to_other_group(
        self, service: AccountGroupService, invitation_repo: MagicMock
    ):
        invitation = make_invitation(group_id=uuid.uuid4())
        invitation_repo.get_invitation_by_id.return_value = invitation

        with pytest.raises(NotFoundError):
            service.revoke_invitation(uuid.uuid4(), invitation.id)

        invitation_repo.delete_invitation_by_id.assert_not_called()


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


class TestBuildProjection:
    def test_flat_curve_without_pending_expenses(self):
        today = date(2026, 3, 10)

        points = build_projection(100_000, [], today, today + timedelta(days=3))

        assert [point.date for point in points] == [
            today + timedelta(days=offset) for offset in range(4)
        ]
        assert [point.balance for point in points] == [100_000] * 4

    def test_step_lands_on_the_due_date(self):
        today = date(2026, 3, 10)
        expense = make_pending_expense(
            amount=10_000, due_date=today + timedelta(days=2)
        )

        points = build_projection(100_000, [expense], today, today + timedelta(days=3))

        assert [point.balance for point in points] == [
            100_000,
            100_000,
            90_000,
            90_000,
        ]

    def test_overdue_expense_is_anchored_to_today(self):
        today = date(2026, 3, 10)
        expense = make_pending_expense(
            amount=10_000, due_date=today - timedelta(days=5)
        )

        points = build_projection(100_000, [expense], today, today + timedelta(days=2))

        assert [point.balance for point in points] == [90_000, 90_000, 90_000]

    def test_two_expenses_on_the_same_day_share_one_step(self):
        today = date(2026, 3, 10)
        due_date = today + timedelta(days=1)
        expenses = [
            make_pending_expense(amount=10_000, due_date=due_date),
            make_pending_expense(amount=5_000, due_date=due_date),
        ]

        points = build_projection(100_000, expenses, today, today + timedelta(days=2))

        assert [point.date for point in points] == [
            today,
            due_date,
            today + timedelta(days=2),
        ]
        assert [point.balance for point in points] == [100_000, 85_000, 85_000]

    def test_payday_today_returns_a_single_point(self):
        today = date(2026, 3, 10)
        expense = make_pending_expense(amount=10_000, due_date=today)

        points = build_projection(100_000, [expense], today, today)

        assert len(points) == 1
        assert points[0].date == today
        assert points[0].balance == 90_000

    def test_last_point_equals_real_balance(self):
        today = date(2026, 3, 10)
        payday = today + timedelta(days=6)
        expenses = [
            make_pending_expense(amount=10_000, due_date=today - timedelta(days=1)),
            make_pending_expense(amount=5_000, due_date=today + timedelta(days=2)),
            make_pending_expense(amount=7_500, due_date=payday),
        ]
        available = 100_000
        real_balance = available - sum(expense.amount for expense in expenses)

        points = build_projection(available, expenses, today, payday)

        assert points[-1].balance == real_balance


class TestPendingFixedExpenses:
    def test_excludes_the_payday_anchor(self):
        payday_plan = make_payment_plan(type=TransactionTypeEnum.INCOME)

        result = pending_fixed_expenses([payday_plan], payday_plan.id)

        assert result == []

    def test_excludes_a_non_anchor_income(self):
        income = make_payment_plan(type=TransactionTypeEnum.INCOME)

        result = pending_fixed_expenses([income], uuid.uuid4())

        assert result == []

    def test_excludes_a_transfer(self):
        # payment_plans.md §6: limitación conocida, una transferencia
        # programada reduce el disponible pero v1 no la cuenta.
        transfer = make_payment_plan(
            type=TransactionTypeEnum.TRANSFER, to_account_id=uuid.uuid4()
        )

        result = pending_fixed_expenses([transfer], uuid.uuid4())

        assert result == []

    def test_includes_an_expense(self):
        expense = make_payment_plan(
            type=TransactionTypeEnum.EXPENSE,
            amount=42_000,
            description="Luz",
            next_due_date=date(2026, 3, 4),
        )

        result = pending_fixed_expenses([expense], uuid.uuid4())

        assert len(result) == 1
        assert result[0].payment_plan_id == expense.id
        assert result[0].amount == 42_000
        assert result[0].description == "Luz"
        assert result[0].due_date == date(2026, 3, 4)


class TestDailySafeSpend:
    def test_does_not_divide_by_zero_on_payday(self):
        assert daily_safe_spend(90_000, 0) == 90_000

    def test_rounds_down(self):
        assert daily_safe_spend(1_000, 3) == 333

    def test_negative_real_balance_does_not_raise(self):
        assert daily_safe_spend(-1_000, 3) == -334


class TestGroupOverview:
    def test_returns_nulls_without_payday_anchor(
        self,
        overview_service: GroupOverviewService,
        account_service: MagicMock,
        payment_plan_service: MagicMock,
        transaction_service: MagicMock,
    ):
        account_service.get_group_balance.return_value = make_group_balance(
            net_worth=500_000, available=100_000
        )
        transaction_service.get_daily_spend.return_value = make_daily_spend(
            spent=2_500, transaction_count=2
        )
        payment_plan_service.get_payday_plan.return_value = None

        result = overview_service.get_group_overview(uuid.uuid4())

        assert result.payday is None
        assert result.days_remaining is None
        assert result.daily_safe_spend is None
        assert result.projection is None
        assert result.net_worth == 500_000
        assert result.available == 100_000
        assert result.spent_today == 2_500
        assert result.transaction_count_today == 2
        assert result.real_balance == 100_000
        payment_plan_service.get_upcoming_payment_plans.assert_not_called()

    def test_composes_forecast_around_the_payday_anchor(
        self,
        overview_service: GroupOverviewService,
        account_service: MagicMock,
        payment_plan_service: MagicMock,
        transaction_service: MagicMock,
    ):
        today = date.today()
        payday = today + timedelta(days=5)
        payday_plan = make_payment_plan(
            type=TransactionTypeEnum.INCOME, amount=200_000, next_due_date=payday
        )
        rent = make_payment_plan(amount=60_000, next_due_date=today + timedelta(days=2))
        account_service.get_group_balance.return_value = make_group_balance(
            available=100_000
        )
        transaction_service.get_daily_spend.return_value = make_daily_spend()
        payment_plan_service.get_payday_plan.return_value = payday_plan
        payment_plan_service.get_upcoming_payment_plans.return_value = [
            payday_plan,
            rent,
        ]

        result = overview_service.get_group_overview(uuid.uuid4())

        assert result.payday is not None
        assert result.payday.date == payday
        assert result.payday.amount == 200_000
        pending_ids = [
            expense.payment_plan_id for expense in result.pending_fixed_expenses
        ]
        assert pending_ids == [rent.id]
        assert result.pending_fixed_expenses_total == 60_000
        assert result.real_balance == 40_000
        assert result.days_remaining == 5
        assert result.daily_safe_spend == 8_000
        assert result.projection is not None
        assert result.projection[-1].date == payday
        assert result.projection[-1].balance == result.real_balance

    def test_overdue_anchor_never_yields_negative_days_remaining(
        self,
        overview_service: GroupOverviewService,
        account_service: MagicMock,
        payment_plan_service: MagicMock,
        transaction_service: MagicMock,
    ):
        # account_groups.md §5: el cron pudo fallar un día y dejar el ancla en
        # el pasado. El horizonte no se cierra antes de hoy.
        today = date.today()
        payday_plan = make_payment_plan(
            type=TransactionTypeEnum.INCOME,
            amount=200_000,
            next_due_date=today - timedelta(days=1),
        )
        account_service.get_group_balance.return_value = make_group_balance(
            available=100_000
        )
        transaction_service.get_daily_spend.return_value = make_daily_spend()
        payment_plan_service.get_payday_plan.return_value = payday_plan
        payment_plan_service.get_upcoming_payment_plans.return_value = [payday_plan]

        result = overview_service.get_group_overview(uuid.uuid4())

        assert result.days_remaining == 0
        # La ventana se pide hasta hoy, no hasta el vencimiento atrasado: si no,
        # un gasto que vence hoy quedaría fuera de real_balance.
        assert payment_plan_service.get_upcoming_payment_plans.call_args.args[1] == (
            today
        )
        assert result.projection is not None
        assert len(result.projection) == 1
        assert result.projection[-1].balance == result.real_balance


class TestUpdateGroupClearingFields:
    """ARCHITECTURE.md §5.5: null explícito vacía; ausente no toca nada."""

    def test_explicit_null_icon_reaches_the_repository(
        self, service: AccountGroupService, account_group_repo: MagicMock
    ):
        membership = make_member(uuid.uuid4(), uuid.uuid4())
        account_group_repo.update_group.return_value = make_group(icon=None)

        service.update_group(membership, UpdateAccountGroupCommand(icon=None))

        applied = account_group_repo.update_group.call_args.args[1]
        assert applied.icon is None
        assert applied.color is UNSET
        assert applied.name is UNSET

    def test_rejects_explicit_null_on_not_null_columns(self):
        for field in ("name", "is_active"):
            with pytest.raises(ValidationError):
                UpdateGroupRequest.model_validate({field: None})
