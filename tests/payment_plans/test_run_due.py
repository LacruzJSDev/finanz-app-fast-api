import uuid
from datetime import date
from unittest.mock import MagicMock, patch

from app.payment_plans.models import FrequencyUnitEnum
from app.payment_plans.run_due import (
    advance_scheduled_date,
    payment_plan_occurrence_id,
    process_due_plan,
)


def test_monthly_recurrence_keeps_calendar_day_22():
    assert advance_scheduled_date(
        date(2027, 9, 22), 1, FrequencyUnitEnum.MONTH, anchor_day=22
    ) == date(2027, 10, 22)


def test_monthly_recurrence_clips_day_31_then_recovers_it():
    february = advance_scheduled_date(
        date(2027, 1, 31), 1, FrequencyUnitEnum.MONTH, anchor_day=31
    )

    assert february == date(2027, 2, 28)
    assert advance_scheduled_date(
        february, 1, FrequencyUnitEnum.MONTH, anchor_day=31
    ) == date(2027, 3, 31)


def test_yearly_recurrence_recovers_february_29_in_a_leap_year():
    non_leap_year = advance_scheduled_date(
        date(2024, 2, 29), 1, FrequencyUnitEnum.YEAR, anchor_day=29
    )

    assert non_leap_year == date(2025, 2, 28)
    assert advance_scheduled_date(
        date(2027, 2, 28), 1, FrequencyUnitEnum.YEAR, anchor_day=29
    ) == date(2028, 2, 29)


def test_occurrence_identifier_is_stable_for_one_scheduled_date():
    plan_id = uuid.uuid4()
    scheduled_for = date(2027, 9, 22)

    assert payment_plan_occurrence_id(
        plan_id, scheduled_for
    ) == payment_plan_occurrence_id(plan_id, scheduled_for)
    assert payment_plan_occurrence_id(
        plan_id, scheduled_for
    ) != payment_plan_occurrence_id(plan_id, date(2027, 10, 22))


def test_process_locks_then_skips_a_plan_already_advanced_by_another_cron():
    db = MagicMock()
    payment_plan_id = uuid.uuid4()
    plan = MagicMock(is_active=True, next_due_date=date(2027, 10, 22))

    with (
        patch("app.payment_plans.run_due.SessionLocal", return_value=db),
        patch("app.payment_plans.run_due.PaymentPlanRepository") as repository_class,
    ):
        repository = repository_class.return_value
        repository.get_payment_plan_by_id.return_value = plan

        process_due_plan(payment_plan_id, today=date(2027, 10, 21))

    repository.get_payment_plan_by_id.assert_called_once_with(
        payment_plan_id,
        for_update=True,
    )
    db.commit.assert_not_called()
    db.close.assert_called_once()
