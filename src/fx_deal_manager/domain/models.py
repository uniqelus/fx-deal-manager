import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DealStateLookup(Base):
    __tablename__ = "deal_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class DealTypeLookup(Base):
    __tablename__ = "deal_type"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class PaymentDirectionLookup(Base):
    __tablename__ = "payment_direction"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)


class ValidationStatusLookup(Base):
    __tablename__ = "validation_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)


class Currency(Base):
    __tablename__ = "currency"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    decimal_places: Mapped[int] = mapped_column(default=2)


class Counterparty(Base):
    __tablename__ = "counterparty"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bic: Mapped[str | None] = mapped_column(String(11))
    country: Mapped[str | None] = mapped_column(String(2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NostroAccount(Base):
    __tablename__ = "nostro_account"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currency.code"), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_number: Mapped[str] = mapped_column(String(34), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BusinessCalendar(Base):
    __tablename__ = "business_calendar"

    calendar_date: Mapped[date] = mapped_column(Date, primary_key=True)
    is_business_day: Mapped[bool] = mapped_column(Boolean, nullable=False)


class FXDeal(Base):
    __tablename__ = "fx_deal"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    buy_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    sell_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    operation_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    counterparty_id: Mapped[str] = mapped_column(ForeignKey("counterparty.id"), nullable=False)
    deal_type_id: Mapped[int] = mapped_column(ForeignKey("deal_type.id"), nullable=False)
    deal_state_id: Mapped[int] = mapped_column(ForeignKey("deal_state.id"), nullable=False)
    validation_status_id: Mapped[int] = mapped_column(
        ForeignKey("validation_status.id"), nullable=False
    )
    trader_id: Mapped[str] = mapped_column(String(36), nullable=False)
    trader_email: Mapped[str] = mapped_column(String(320), nullable=False)
    positioner_id: Mapped[str | None] = mapped_column(String(36))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    deal_type: Mapped[DealTypeLookup] = relationship(lazy="joined")
    deal_state: Mapped[DealStateLookup] = relationship(lazy="joined")
    validation_status: Mapped[ValidationStatusLookup] = relationship(lazy="joined")
    counterparty: Mapped[Counterparty] = relationship(lazy="joined")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", lazy="selectin"
    )
    positioner_solution: Mapped["PositionerSolution | None"] = relationship(
        back_populates="deal", uselist=False, lazy="selectin"
    )


class Payment(Base):
    __tablename__ = "payment"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fx_deal.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currency.code"), nullable=False)
    account_code: Mapped[str | None] = mapped_column(String(30))
    payment_direction_id: Mapped[int] = mapped_column(
        ForeignKey("payment_direction.id"), nullable=False
    )
    value_date: Mapped[date | None] = mapped_column(Date)

    deal: Mapped[FXDeal] = relationship(back_populates="payments")
    payment_direction: Mapped[PaymentDirectionLookup] = relationship(lazy="joined")


class PositionerSolution(Base):
    __tablename__ = "positioner_solution"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fx_deal.id", ondelete="CASCADE"), unique=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    positioner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    deal: Mapped[FXDeal] = relationship(back_populates="positioner_solution")


class AuditLogEntry(Base):
    __tablename__ = "audit_log_entry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
