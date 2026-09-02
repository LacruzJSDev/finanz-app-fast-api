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
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, enum_values


class TransactionTypeEnum(str, enum.Enum):
    """Naturaleza de una transacción. transfer no es ni ingreso ni gasto,
    es un movimiento interno entre dos cuentas del mismo grupo."""

    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class Transaction(Base):
    """Movimiento real registrado en una cuenta. Una transferencia se
    representa como DOS filas (partida doble), una por cuenta, enlazadas
    por transfer_group_id — no como una sola fila con dos cuentas. Así
    balance = suma de amount de las filas de una cuenta vale siempre,
    sin caso especial para transfer (ver transactions.md §5).
    """

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            "type != 'transfer' OR category_id IS NULL",
            name="transfer_no_category",
        ),
        CheckConstraint(
            "payment_plan_id IS NULL OR payment_plan_occurrence_id IS NOT NULL",
            name="payment_plan_occurrence_required",
        ),
        # Una misma ocurrencia programada solo puede afectar una vez a cada
        # cuenta. Para una transferencia las dos patas tienen cuentas
        # distintas, así que ambas caben; una repetición completa colisiona
        # en la primera fila y se revierte como unidad.
        Index(
            "uq_transactions_payment_plan_occurrence_account",
            "payment_plan_occurrence_id",
            "account_id",
            unique=True,
            postgresql_where=text("payment_plan_occurrence_id IS NOT NULL"),
        ),
        CheckConstraint(
            "(type = 'transfer' AND to_account_id IS NOT NULL "
            "AND to_account_id != account_id) "
            "OR (type != 'transfer' AND to_account_id IS NULL)",
            name="transfer_to_account",
        ),
        CheckConstraint(
            "(type = 'transfer' AND transfer_group_id IS NOT NULL) "
            "OR (type != 'transfer' AND transfer_group_id IS NULL)",
            name="transfer_group",
        ),
        CheckConstraint(
            "(type = 'income' AND amount > 0) OR (type = 'expense' AND amount < 0) "
            "OR (type = 'transfer' AND amount != 0)",
            name="amount_sign",
        ),
        Index(
            "ix_transactions_transfer_group_id",
            "transfer_group_id",
            postgresql_where=text("transfer_group_id IS NOT NULL"),
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
    payment_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_plans.id", ondelete="SET NULL"),
        index=True,
    )
    # Identificador determinista derivado de (plan, fecha programada). Las dos
    # patas de una transferencia lo comparten para que la restricción anterior
    # pueda rechazar una segunda materialización completa.
    payment_plan_occurrence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    # Sin ForeignKey propia: solo enlaza entre sí las dos patas de una
    # misma transferencia (mismo valor en ambas filas), no referencia a
    # ninguna otra tabla.
    transfer_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    amount: Mapped[int] = mapped_column(BigInteger)
    type: Mapped[TransactionTypeEnum] = mapped_column(
        Enum(
            TransactionTypeEnum,
            name="transaction_type_enum",
            values_callable=enum_values,
        ),
        index=True,
    )
    date: Mapped[date_] = mapped_column(Date, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    # Identificador, en texto, del documento correspondiente en MongoDB
    # cuando la transacción se originó a partir de un recibo escaneado por
    # OCR — sin FK real, al ser un motor de base de datos distinto. Ningún
    # endpoint de v1 la lee ni la escribe (transactions.md §6).
    ocr_receipt_ref: Mapped[str | None] = mapped_column(String(64))
    # Borrado lógico: la única excepción del proyecto al borrado físico
    # por defecto (ARCHITECTURE.md §8.2), por integridad del histórico.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
