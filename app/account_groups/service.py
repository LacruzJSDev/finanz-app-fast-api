import secrets
import uuid
from dataclasses import dataclass
from datetime import date as date_
from datetime import datetime, timedelta, timezone

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
from app.account_groups.repository import (
    AccountGroupMemberRepository,
    AccountGroupsRepository,
    InvitationRepository,
)
from app.account_groups.schemas import (
    GroupMemberRead,
    GroupOverviewRead,
    GroupRead,
    InvitationRead,
    InvitedByRead,
    PaydayRead,
    PendingFixedExpenseRead,
    ProjectionPointRead,
)
from app.accounts.service import AccountService
from app.payment_plans.schemas import PaymentPlanRead
from app.payment_plans.service import PaymentPlanService
from app.shared.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.transactions.commands import DailySpendCommand
from app.transactions.models import TransactionTypeEnum
from app.transactions.service import TransactionService
from app.users.models import User
from app.users.repository import UserRepository


@dataclass
class AccountGroupService:
    """Lógica de negocio del dominio account_groups."""

    account_group_repo: AccountGroupsRepository
    account_group_member_repo: AccountGroupMemberRepository
    user_repo: UserRepository
    invitation_repo: InvitationRepository

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

    def _to_invitation_read(
        self, invitation: Invitation, user: User | None
    ) -> InvitationRead:
        invited_by = InvitedByRead(name=user.name, email=user.email) if user else None
        invitation_read = InvitationRead(
            id=invitation.id,
            group_id=invitation.group_id,
            invited_by=invited_by,
            role=invitation.role,
            code=invitation.code,
            status=invitation.status,
            accepted_by=invitation.accepted_by,
            accepted_at=invitation.accepted_at,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )
        return invitation_read

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

    def create_invitation(
        self, group_id: uuid.UUID, user_id: uuid.UUID, role: AccountGroupMemberRoleEnum
    ) -> InvitationRead:

        code = secrets.token_urlsafe(15)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=7)

        invitation_command = InvitationCommand(
            group_id=group_id,
            invited_by=user_id,
            role=role,
            code=code,
            expires_at=expires_at,
        )
        invitation = self.invitation_repo.create_invitation(invitation_command)
        if invitation.invited_by is None:
            raise ConflictError("El usuario que te invitó no existe")

        invited_by = self.user_repo.get_user_by_id(invitation.invited_by)
        if invited_by is None:
            raise ConflictError("El usuario que te invitó no existe")

        invitation_read = self._to_invitation_read(invitation, invited_by)
        return invitation_read

    def get_invitation(self, code: str) -> InvitationRead:
        invitation = self.invitation_repo.get_invitation_by_code(code)
        if invitation is None:
            raise NotFoundError("Invitación no encontrada")

        now = datetime.now(timezone.utc)
        if invitation.expires_at < now or invitation.invited_by is None:
            expired_invitation = self.invitation_repo.expire_invitation_by_id(
                invitation.id
            )
            return self._to_invitation_read(expired_invitation, None)

        invited_by = self.user_repo.get_user_by_id(invitation.invited_by)
        return self._to_invitation_read(invitation, invited_by)

    def accept_invitation(
        self, group_id: uuid.UUID, user_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> InvitationRead:
        members = self.account_group_member_repo.get_group_members_by_group_id(group_id)
        members_ids = {member.user_id for member in members}
        if user_id in members_ids:
            raise ConflictError("El usuario ya pertenece al grupo")

        invitation = self.invitation_repo.get_invitation_by_id(invitation_id)

        now = datetime.now(timezone.utc)
        if invitation is None or invitation.group_id != group_id:
            raise NotFoundError("Invitación no encontrada")
        if (
            invitation.expires_at < now
            or invitation.invited_by is None
            or invitation.status == InvitationStatusEnum.EXPIRED
        ):
            if invitation.status == InvitationStatusEnum.PENDING:
                self.invitation_repo.expire_invitation_by_id(invitation_id)
            raise ConflictError("La invitación ha expirado")
        if invitation.status == InvitationStatusEnum.ACCEPTED:
            raise ConflictError("La invitación ya ha sido aceptada")

        accepted_invitation = self.invitation_repo.accept_invitation_by_id(
            invitation_id, now, user_id
        )
        invited_by = self.user_repo.get_user_by_id(invitation.invited_by)
        invitation_read = self._to_invitation_read(accepted_invitation, invited_by)
        account_group_member_command = AccountGroupMemberCommand(
            group_id=group_id,
            user_id=user_id,
            role=invitation.role,
        )
        self.account_group_member_repo.create_account_group_member(
            account_group_member_command
        )
        return invitation_read


def pending_fixed_expenses(
    upcoming: list[PaymentPlanRead], payday_plan_id: uuid.UUID
) -> list[PendingFixedExpenseRead]:
    return [
        PendingFixedExpenseRead(
            payment_plan_id=plan.id,
            description=plan.description,
            amount=plan.amount,
            due_date=plan.next_due_date,
        )
        for plan in upcoming
        if plan.id != payday_plan_id and plan.type == TransactionTypeEnum.EXPENSE
    ]


def daily_safe_spend(real_balance: int, days_remaining: int) -> int:
    return real_balance // max(days_remaining, 1)


def build_projection(
    available: int,
    expenses: list[PendingFixedExpenseRead],
    today: date_,
    payday: date_,
) -> list[ProjectionPointRead]:
    steps: dict[date_, int] = {}
    for expense in expenses:
        due_date = max(expense.due_date, today)
        steps[due_date] = steps.get(due_date, 0) + expense.amount

    points: list[ProjectionPointRead] = []
    balance = available
    day = today
    # Un ancla atrasada (el cron aún no ha corrido) dejaría la curva vacía, y
    # con ella se perdería la igualdad con real_balance del último punto.
    last_day = max(payday, today)
    while day <= last_day:
        balance -= steps.get(day, 0)
        points.append(ProjectionPointRead(date=day, balance=balance))
        day += timedelta(days=1)
    return points


@dataclass
class GroupOverviewService:
    """Composición del resumen de grupo (account_groups.md §4)."""

    account_service: AccountService
    payment_plan_service: PaymentPlanService
    transaction_service: TransactionService

    def get_group_overview(self, group_id: uuid.UUID) -> GroupOverviewRead:
        # Un único today para todos los bloques: es la razón de ser del
        # endpoint (account_groups.md §4).
        today = date_.today()

        balance = self.account_service.get_group_balance(group_id)
        daily_spend = self.transaction_service.get_daily_spend(
            DailySpendCommand(group_id=group_id, date=today)
        )
        payday_plan = self.payment_plan_service.get_payday_plan(group_id)

        if payday_plan is None:
            return GroupOverviewRead(
                net_worth=balance.net_worth,
                available=balance.available,
                account_count=balance.account_count,
                spent_today=daily_spend.spent,
                transaction_count_today=daily_spend.transaction_count,
                payday=None,
                pending_fixed_expenses=[],
                pending_fixed_expenses_total=0,
                real_balance=balance.available,
                days_remaining=None,
                daily_safe_spend=None,
                projection=None,
            )

        payday_date = payday_plan.next_due_date
        # account_groups.md §5: el cron puede no haber corrido aún, o haber
        # fallado un día, y dejar next_due_date en el pasado. El horizonte no
        # se cierra nunca antes de hoy — si no, un gasto que vence hoy quedaría
        # fuera de real_balance y days_remaining saldría negativo.
        horizon = max(payday_date, today)
        upcoming = self.payment_plan_service.get_upcoming_payment_plans(
            group_id, horizon
        )
        expenses = pending_fixed_expenses(upcoming, payday_plan.id)
        expenses_total = sum(expense.amount for expense in expenses)
        real_balance = balance.available - expenses_total
        days_remaining = (horizon - today).days

        return GroupOverviewRead(
            net_worth=balance.net_worth,
            available=balance.available,
            account_count=balance.account_count,
            spent_today=daily_spend.spent,
            transaction_count_today=daily_spend.transaction_count,
            payday=PaydayRead(date=payday_date, amount=payday_plan.amount),
            pending_fixed_expenses=expenses,
            pending_fixed_expenses_total=expenses_total,
            real_balance=real_balance,
            days_remaining=days_remaining,
            daily_safe_spend=daily_safe_spend(real_balance, days_remaining),
            projection=build_projection(balance.available, expenses, today, horizon),
        )
