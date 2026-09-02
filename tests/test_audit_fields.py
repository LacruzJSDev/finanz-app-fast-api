import uuid
from unittest.mock import MagicMock

from app.accounts.commands import UpdateAccountCommand
from app.accounts.repository import AccountRepository
from app.categories.commands import UpdateCategoryCommand
from app.categories.repository import CategoryRepository
from app.payment_plans.commands import UpdatePaymentPlanCommand
from app.payment_plans.repository import PaymentPlanRepository
from app.transactions.commands import UpdateTransactionCommand
from app.transactions.repository import TransactionRepository


def updated_by_from_statement(db: MagicMock) -> uuid.UUID | None:
    statement = db.execute.call_args.args[0]
    return statement.compile().params["updated_by"]


def test_account_update_records_the_actor() -> None:
    db = MagicMock()
    actor_id = uuid.uuid4()

    AccountRepository(db).update_account(
        uuid.uuid4(), UpdateAccountCommand(name="Renombrada"), actor_id
    )

    assert updated_by_from_statement(db) == actor_id


def test_category_update_records_the_actor() -> None:
    db = MagicMock()
    actor_id = uuid.uuid4()

    CategoryRepository(db).update_category(
        uuid.uuid4(), UpdateCategoryCommand(name="Comida"), actor_id
    )

    assert updated_by_from_statement(db) == actor_id


def test_payment_plan_update_records_the_actor() -> None:
    db = MagicMock()
    actor_id = uuid.uuid4()

    PaymentPlanRepository(db).update_payment_plan(
        uuid.uuid4(), UpdatePaymentPlanCommand(description="Alquiler"), actor_id
    )

    assert updated_by_from_statement(db) == actor_id


def test_transaction_update_records_the_actor() -> None:
    db = MagicMock()
    actor_id = uuid.uuid4()

    TransactionRepository(db).update_transaction(
        uuid.uuid4(), UpdateTransactionCommand(notes="Corregida"), actor_id
    )

    assert updated_by_from_statement(db) == actor_id


def test_transaction_soft_delete_records_the_actor() -> None:
    db = MagicMock()
    actor_id = uuid.uuid4()

    TransactionRepository(db).delete_transaction(uuid.uuid4(), actor_id)

    assert updated_by_from_statement(db) == actor_id
