"""Garantías que solo PostgreSQL puede demostrar para las transferencias."""

import uuid
from collections.abc import Mapping
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


def _seed_accounts(connection: Connection) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    group_a_id, group_b_id = uuid.uuid4(), uuid.uuid4()
    source_id, destination_id, other_group_account_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    connection.execute(
        text("INSERT INTO account_groups (id, name) VALUES (:id, :name)"),
        [{"id": group_a_id, "name": "A"}, {"id": group_b_id, "name": "B"}],
    )
    connection.execute(
        text(
            """
            INSERT INTO accounts (id, group_id, name, currency)
            VALUES (:id, :group_id, :name, 'EUR')
            """
        ),
        [
            {"id": source_id, "group_id": group_a_id, "name": "Origen"},
            {"id": destination_id, "group_id": group_a_id, "name": "Destino"},
            {
                "id": other_group_account_id,
                "group_id": group_b_id,
                "name": "Ajena",
            },
        ],
    )
    return source_id, destination_id, other_group_account_id


def _assert_rejected_by_trigger(
    connection: Connection, statement: str, params: Mapping[str, object]
) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(IntegrityError, match="mismo grupo|grupos distintos"):
            connection.execute(text(statement), params)
    finally:
        savepoint.rollback()


def test_transaction_trigger_rejects_cross_group_transfer_insert_and_update(
    migrated_database: Engine,
) -> None:
    with migrated_database.begin() as connection:
        source_id, destination_id, other_group_account_id = _seed_accounts(connection)
        transaction_id, transfer_group_id = uuid.uuid4(), uuid.uuid4()
        params = {
            "id": transaction_id,
            "source": source_id,
            "destination": other_group_account_id,
            "transfer_group_id": transfer_group_id,
            "date": date(2026, 9, 2),
        }
        _assert_rejected_by_trigger(
            connection,
            """
            INSERT INTO transactions
                (id, account_id, to_account_id, transfer_group_id,
                 type, amount, date)
            VALUES
                (:id, :source, :destination, :transfer_group_id,
                 'transfer', -1, :date)
            """,
            params,
        )

        connection.execute(
            text(
                """
                INSERT INTO transactions
                    (id, account_id, to_account_id, transfer_group_id,
                     type, amount, date)
                VALUES
                    (:id, :source, :destination, :transfer_group_id,
                     'transfer', -1, :date)
                """
            ),
            {**params, "destination": destination_id},
        )
        _assert_rejected_by_trigger(
            connection,
            "UPDATE transactions SET to_account_id = :destination WHERE id = :id",
            {"id": transaction_id, "destination": other_group_account_id},
        )


def test_payment_plan_trigger_rejects_cross_group_transfer_insert_and_update(
    migrated_database: Engine,
) -> None:
    with migrated_database.begin() as connection:
        source_id, destination_id, other_group_account_id = _seed_accounts(connection)
        plan_id = uuid.uuid4()
        params = {
            "id": plan_id,
            "source": source_id,
            "destination": other_group_account_id,
            "due_date": date(2026, 9, 2),
        }
        _assert_rejected_by_trigger(
            connection,
            """
            INSERT INTO payment_plans
                (id, account_id, to_account_id, type, amount, next_due_date,
                 is_recurring, frequency_interval, frequency_unit,
                 recurrence_anchor_day)
            VALUES
                (:id, :source, :destination, 'transfer', 1, :due_date,
                 true, 1, 'month', 2)
            """,
            params,
        )

        connection.execute(
            text(
                """
                INSERT INTO payment_plans
                    (id, account_id, to_account_id, type, amount, next_due_date,
                     is_recurring, frequency_interval, frequency_unit,
                     recurrence_anchor_day)
                VALUES
                    (:id, :source, :destination, 'transfer', 1, :due_date,
                     true, 1, 'month', 2)
                """
            ),
            {**params, "destination": destination_id},
        )
        _assert_rejected_by_trigger(
            connection,
            "UPDATE payment_plans SET to_account_id = :destination WHERE id = :id",
            {"id": plan_id, "destination": other_group_account_id},
        )
