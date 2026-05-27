from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fx_deal_manager.domain.enums import (
    DealState,
    DealType,
    OperationDirection,
    PaymentDirection,
    ValidationStatus,
)


class UserClaims(BaseModel):
    user_id: str
    email: str
    first_name: str
    last_name: str
    role: str
    expires_at: int = Field(description="Unix timestamp (exp claim)")


class MeResponse(BaseModel):
    user_id: str
    email: str
    first_name: str
    last_name: str
    role: str


class MeProfileResponse(MeResponse):
    phone: str | None = None
    department: str | None = None


class MeProfileUpdateRequest(BaseModel):
    phone: str | None = Field(default=None, max_length=40)
    department: str | None = Field(default=None, max_length=120)


class DealCreateRequest(BaseModel):
    trade_date: date
    deal_type: DealType
    operation_direction: OperationDirection
    buy_currency: str = Field(min_length=3, max_length=3)
    sell_currency: str = Field(min_length=3, max_length=3)
    amount: Decimal = Field(gt=0)
    rate: Decimal = Field(gt=0)
    counterparty_id: str = Field(min_length=1, max_length=20)
    value_date: date | None = None
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("buy_currency", "sell_currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


class DealUpdateRequest(BaseModel):
    trade_date: date | None = None
    deal_type: DealType | None = None
    operation_direction: OperationDirection | None = None
    buy_currency: str | None = Field(default=None, min_length=3, max_length=3)
    sell_currency: str | None = Field(default=None, min_length=3, max_length=3)
    amount: Decimal | None = Field(default=None, gt=0)
    rate: Decimal | None = Field(default=None, gt=0)
    counterparty_id: str | None = Field(default=None, min_length=1, max_length=20)
    value_date: date | None = None
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("buy_currency", "sell_currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount: Decimal
    currency_code: str
    account_code: str | None
    payment_direction: PaymentDirection
    value_date: date | None


class DealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trade_date: date
    value_date: date | None
    deal_type: DealType
    operation_direction: OperationDirection
    buy_currency: str
    sell_currency: str
    amount: Decimal
    rate: Decimal
    counterparty_id: str
    counterparty_name: str | None = None
    status: DealState
    validation_status: ValidationStatus
    trader_id: str
    trader_email: str
    positioner_id: str | None
    comment: str | None
    payments: list[PaymentResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DealListResponse(BaseModel):
    items: list[DealResponse]
    total: int
    page: int
    page_size: int


class ValidationErrorDetail(BaseModel):
    field: str
    message: str


class CounterpartyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    bic: str | None
    country: str | None
    is_active: bool


class CurrencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    decimal_places: int


class NostroAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    currency_code: str
    bank_name: str
    account_number: str
    is_active: bool


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_id: UUID
    entity_type: str
    action: str
    old_value: str | None
    new_value: str | None
    created_at: datetime
    created_by: str


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse]
    total: int
    page: int
    page_size: int


class PositionerCommentRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)


class NsiSyncResponse(BaseModel):
    synced: bool
    counterparties: int
    message: str


class FxPositionAccountResponse(BaseModel):
    account_number: str
    name: str | None = None
    currency_code: str
    opening_balance: Decimal | None = None
    turnover_in: Decimal | None = None
    turnover_out: Decimal | None = None
    current_position: Decimal | None = None
    source: str


class FxPositionCurrencyResponse(BaseModel):
    currency_code: str
    current_position: Decimal
    open_exposure: Decimal
    projected_position: Decimal


class FxPositionsResponse(BaseModel):
    date: date
    source: str
    accounts: list[FxPositionAccountResponse]
    currencies: list[FxPositionCurrencyResponse]


class QuoteResponse(BaseModel):
    pair: str
    base_currency: str
    quote_currency: str
    mid: Decimal
    bid: Decimal
    ask: Decimal
    spread: Decimal
    delta_percent: Decimal
    source: str
    updated_at: datetime


class NotificationResponse(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    kind: str
    created_at: datetime
    read: bool
    entity_id: UUID
    entity_type: str
    action: str
    related_url: str | None = None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    unread_count: int
    total: int
