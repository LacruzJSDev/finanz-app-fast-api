import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, enum_values


class AccountTypeEnum(str, enum.Enum):
    """Tipos de cuenta financiera aceptados."""

    CASH = "cash"
    BANK = "bank"
    CREDIT_CARD = "credit_card"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    OTHER = "other"


# accounts.md §5 y ADR-0004. CREDIT_CARD entra aquí porque su balance es deuda
# (negativo): al sumarlo al disponible lo reduce, que es justo lo que toca.
SPENDABLE_ACCOUNT_TYPES = (
    AccountTypeEnum.CASH,
    AccountTypeEnum.BANK,
    AccountTypeEnum.CREDIT_CARD,
)


class Account(Base):
    """Cuenta financiera de un grupo. balance es derivado: nace de
    opening_balance vía trigger y a partir de ahí solo lo tocan los
    triggers de transactions — la aplicación nunca lo escribe directamente.
    """

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account_groups.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[AccountTypeEnum] = mapped_column(
        Enum(
            AccountTypeEnum,
            name="account_type_enum",
            values_callable=enum_values,
        ),
        server_default=text("'bank'"),
    )
    opening_balance: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    balance: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), server_default=text("'EUR'"))
    color: Mapped[str | None] = mapped_column(String(7))
    icon: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
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
