import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Budget(Base):
    """Periodo de vigencia de un presupuesto mensual de una categoría.

    No hay una fila por mes: hay una fila por periodo, con valid_to nulo en
    el vigente (ADR-0005). El solape entre periodos de la misma categoría lo
    impide excl_budget_overlap, un EXCLUDE USING gist que no tiene
    equivalente declarativo aquí y vive en la migración.
    """

    __tablename__ = "budgets"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # Sin index=True: el índice gist que crea excl_budget_overlap ya sirve
    # las búsquedas por categoría (docs/schema-reference.sql).
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
    )
    amount: Mapped[int] = mapped_column(BigInteger)
    valid_from: Mapped[date_] = mapped_column(Date)
    valid_to: Mapped[date_ | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
