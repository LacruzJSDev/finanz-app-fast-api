"""harden payment plan materialization

Revision ID: 4f8d9a2b6c71
Revises: 13e72ce54352
Create Date: 2026-09-02 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f8d9a2b6c71"
down_revision: Union[str, Sequence[str], None] = "13e72ce54352"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persist calendar anchors and deduplicate scheduled occurrences."""
    op.add_column(
        "payment_plans",
        sa.Column("recurrence_anchor_day", sa.Integer(), nullable=True),
    )
    # Todas las filas recurrentes heredadas toman como ancla el día de su
    # próximo vencimiento. Es la única información disponible antes de que la
    # columna exista y conserva la cadencia que tenían al migrar.
    op.execute(
        """
        UPDATE payment_plans
        SET recurrence_anchor_day = EXTRACT(DAY FROM next_due_date)::integer
        WHERE is_recurring = TRUE;
        """
    )
    op.create_check_constraint(
        op.f("ck_payment_plans_recurrence_anchor_day_consistent"),
        "payment_plans",
        "(is_recurring = TRUE AND recurrence_anchor_day BETWEEN 1 AND 31) "
        "OR (is_recurring = FALSE AND recurrence_anchor_day IS NULL)",
    )

    op.add_column(
        "transactions",
        sa.Column("payment_plan_occurrence_id", sa.UUID(), nullable=True),
    )
    # Las transacciones antiguas pueden contener duplicados producidos antes
    # de esta garantía. Se les asigna un valor por fila para que una migración
    # de producción no falle; las ocurrencias nuevas usan un UUID determinista
    # de (plan, fecha) y quedan protegidas por el índice único de abajo.
    op.execute(
        """
        UPDATE transactions
        SET payment_plan_occurrence_id =
            md5('legacy-payment-plan-transaction:' || id::text)::uuid
        WHERE payment_plan_id IS NOT NULL;
        """
    )
    op.create_check_constraint(
        op.f("ck_transactions_payment_plan_occurrence_required"),
        "transactions",
        "payment_plan_id IS NULL OR payment_plan_occurrence_id IS NOT NULL",
    )
    op.create_index(
        "uq_transactions_payment_plan_occurrence_account",
        "transactions",
        ["payment_plan_occurrence_id", "account_id"],
        unique=True,
        postgresql_where=sa.text("payment_plan_occurrence_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove the materialization safety metadata."""
    op.drop_index(
        "uq_transactions_payment_plan_occurrence_account",
        table_name="transactions",
    )
    op.drop_constraint(
        op.f("ck_transactions_payment_plan_occurrence_required"),
        "transactions",
        type_="check",
    )
    op.drop_column("transactions", "payment_plan_occurrence_id")

    op.drop_constraint(
        op.f("ck_payment_plans_recurrence_anchor_day_consistent"),
        "payment_plans",
        type_="check",
    )
    op.drop_column("payment_plans", "recurrence_anchor_day")
