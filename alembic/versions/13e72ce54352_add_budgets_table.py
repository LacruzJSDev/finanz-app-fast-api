"""add budgets table

Revision ID: 13e72ce54352
Revises: 10716e6808f4
Create Date: 2026-08-28 16:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "13e72ce54352"
down_revision: Union[str, Sequence[str], None] = "10716e6808f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Primera extensión del proyecto (ADR-0005): sin ella un EXCLUDE no puede
    # combinar una columna escalar (WITH =) con un rango (WITH &&).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")
    op.create_table(
        "budgets",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_budgets_amount_positive")),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name=op.f("ck_budgets_period"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_budgets_category_id_categories"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_budgets_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_budgets_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
    )
    # Va con op.execute() y no en __table_args__ del modelo: SQLAlchemy tiene
    # ExcludeConstraint, pero --autogenerate no compara restricciones EXCLUDE,
    # así que declararla allí daría la falsa impresión de que Alembic la
    # vigila. Mismo criterio que con los triggers.
    #
    # El índice gist que crea esta restricción ya sirve las búsquedas por
    # categoría: no hace falta un btree adicional sobre category_id.
    op.execute(
        """
            ALTER TABLE budgets
                ADD CONSTRAINT excl_budget_overlap
                EXCLUDE USING gist (
                    category_id WITH =,
                    daterange(valid_from, valid_to, '[)') WITH &&
                );
            """
    )
    op.execute(
        """
            CREATE TRIGGER trg_budgets_set_updated_at
                BEFORE UPDATE ON budgets
                FOR EACH ROW
                EXECUTE FUNCTION set_updated_at();
            """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("budgets")
    # IF EXISTS y sin CASCADE: si alguien más acabara dependiendo de la
    # extensión, este downgrade falla en vez de llevársela por delante.
    op.execute("DROP EXTENSION IF EXISTS btree_gist;")
