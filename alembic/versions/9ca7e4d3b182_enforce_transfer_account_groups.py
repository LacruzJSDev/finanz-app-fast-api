"""enforce transfer account groups

Revision ID: 9ca7e4d3b182
Revises: 4f8d9a2b6c71
Create Date: 2026-09-02 10:20:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9ca7e4d3b182"
down_revision: Union[str, Sequence[str], None] = "4f8d9a2b6c71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Prevent transfers and scheduled transfers from crossing groups."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_transaction_transfer_account_group()
        RETURNS TRIGGER AS $$
        DECLARE
            source_group_id UUID;
            destination_group_id UUID;
        BEGIN
            IF NEW.to_account_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT group_id INTO source_group_id
            FROM accounts WHERE id = NEW.account_id;
            SELECT group_id INTO destination_group_id
            FROM accounts WHERE id = NEW.to_account_id;
            IF source_group_id IS DISTINCT FROM destination_group_id THEN
                RAISE EXCEPTION
                    'Las cuentas de una transferencia deben pertenecer al mismo grupo'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_check_transaction_transfer_account_group
            BEFORE INSERT OR UPDATE OF account_id, to_account_id ON transactions
            FOR EACH ROW
            EXECUTE FUNCTION check_transaction_transfer_account_group();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_payment_plan_transfer_account_group()
        RETURNS TRIGGER AS $$
        DECLARE
            source_group_id UUID;
            destination_group_id UUID;
        BEGIN
            IF NEW.to_account_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT group_id INTO source_group_id
            FROM accounts WHERE id = NEW.account_id;
            SELECT group_id INTO destination_group_id
            FROM accounts WHERE id = NEW.to_account_id;
            IF source_group_id IS DISTINCT FROM destination_group_id THEN
                RAISE EXCEPTION
                    'Cuentas de plan de transferencia de grupos distintos'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_check_payment_plan_transfer_account_group
            BEFORE INSERT OR UPDATE OF account_id, to_account_id ON payment_plans
            FOR EACH ROW
            EXECUTE FUNCTION check_payment_plan_transfer_account_group();
        """
    )


def downgrade() -> None:
    """Remove the database-side transfer group guards."""
    op.execute(
        """
        DROP TRIGGER trg_check_payment_plan_transfer_account_group ON payment_plans;
        DROP FUNCTION check_payment_plan_transfer_account_group();
        DROP TRIGGER trg_check_transaction_transfer_account_group ON transactions;
        DROP FUNCTION check_transaction_transfer_account_group();
        """
    )
