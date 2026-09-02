import enum
import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, enum_values
from app.transactions.models import TransactionTypeEnum


class FrequencyUnitEnum(str, enum.Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class PaymentPlan(Base):
    __tablename__ = "payment_plans"
    __table_args__ = (
        CheckConstraint(
            "(is_recurring = TRUE AND frequency_interval IS NOT NULL "
            "AND frequency_unit IS NOT NULL) "
            "OR (is_recurring = FALSE AND frequency_interval IS NULL "
            "AND frequency_unit IS NULL AND end_date IS NULL)",
            name="recurring_fields",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= next_due_date",
            name="end_date_after_due",
        ),
        CheckConstraint(
            "(is_recurring = TRUE AND recurrence_anchor_day BETWEEN 1 AND 31) "
            "OR (is_recurring = FALSE AND recurrence_anchor_day IS NULL)",
            name="recurrence_anchor_day_consistent",
        ),
        CheckConstraint(
            "(type = 'transfer' AND to_account_id IS NOT NULL "
            "AND to_account_id != account_id) "
            "OR (type != 'transfer' AND to_account_id IS NULL)",
            name="transfer_account",
        ),
        CheckConstraint(
            "type != 'transfer' OR category_id IS NULL",
            name="transfer_no_category",
        ),
        Index(
            "ix_payment_plans_next_due_date",
            "next_due_date",
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
    )
    to_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
    )
    type: Mapped[TransactionTypeEnum] = mapped_column(
        Enum(
            TransactionTypeEnum,
            name="transaction_type_enum",
            values_callable=enum_values,
        )
    )
    amount: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str | None] = mapped_column(Text)
    next_due_date: Mapped[date_] = mapped_column(Date)
    # Día original elegido por el usuario. next_due_date puede estar recortado
    # (p. ej. 28 de febrero para un ancla 31), pero el siguiente mes con 31
    # debe recuperar el día original.
    recurrence_anchor_day: Mapped[int | None] = mapped_column(Integer)
    end_date: Mapped[date_ | None] = mapped_column(Date)
    is_recurring: Mapped[bool] = mapped_column(server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    frequency_interval: Mapped[int | None] = mapped_column(Integer)
    frequency_unit: Mapped[FrequencyUnitEnum | None] = mapped_column(
        Enum(
            FrequencyUnitEnum,
            name="frequency_unit_enum",
            values_callable=enum_values,
        )
    )
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
