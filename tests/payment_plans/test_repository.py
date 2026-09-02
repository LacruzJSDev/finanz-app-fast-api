import uuid
from datetime import date
from typing import cast
from unittest.mock import MagicMock

from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.payment_plans.commands import CreatePaymentPlanCommand
from app.payment_plans.models import FrequencyUnitEnum
from app.payment_plans.repository import PaymentPlanRepository
from app.transactions.models import Transaction, TransactionTypeEnum


def test_recurring_plan_persists_its_original_calendar_day():
    db = MagicMock()
    command = CreatePaymentPlanCommand(
        account_id=uuid.uuid4(),
        group_id=uuid.uuid4(),
        type=TransactionTypeEnum.EXPENSE,
        amount=1_000,
        category_id=None,
        to_account_id=None,
        description=None,
        next_due_date=date(2026, 1, 31),
        end_date=None,
        is_recurring=True,
        frequency_interval=1,
        frequency_unit=FrequencyUnitEnum.MONTH,
    )

    PaymentPlanRepository(db).create_payment_plan(uuid.uuid4(), command)

    created = db.add.call_args.args[0]
    assert created.recurrence_anchor_day == 31


def test_locked_payment_plan_read_uses_postgresql_row_lock():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None

    PaymentPlanRepository(db).get_payment_plan_by_id(uuid.uuid4(), for_update=True)

    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql


def test_occurrence_index_allows_transfer_legs_but_rejects_repeated_leg():
    transaction_table = cast(Table, Transaction.__table__)
    index = next(
        index
        for index in transaction_table.indexes
        if index.name == "uq_transactions_payment_plan_occurrence_account"
    )

    sql = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "UNIQUE" in sql
    assert "payment_plan_occurrence_id, account_id" in sql
    assert "WHERE payment_plan_occurrence_id IS NOT NULL" in sql
