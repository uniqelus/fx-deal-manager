"""Initial schema with lookup tables and NSI seed data.

Revision ID: 001
Revises:
Create Date: 2026-05-24
"""

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deal_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
    )
    op.create_table(
        "deal_type",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
    )
    op.create_table(
        "payment_direction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=10), nullable=False, unique=True),
    )
    op.create_table(
        "validation_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=20), nullable=False, unique=True),
    )
    op.create_table(
        "currency",
        sa.Column("code", sa.String(length=3), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("decimal_places", sa.Integer(), nullable=False, server_default="2"),
    )
    op.create_table(
        "counterparty",
        sa.Column("id", sa.String(length=20), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("bic", sa.String(length=11)),
        sa.Column("country", sa.String(length=2)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "nostro_account",
        sa.Column("id", sa.String(length=30), primary_key=True),
        sa.Column("currency_code", sa.String(length=3), sa.ForeignKey("currency.code"), nullable=False),
        sa.Column("bank_name", sa.String(length=255), nullable=False),
        sa.Column("account_number", sa.String(length=34), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "business_calendar",
        sa.Column("calendar_date", sa.Date(), primary_key=True),
        sa.Column("is_business_day", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "fx_deal",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("value_date", sa.Date()),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("buy_currency", sa.String(length=3), nullable=False),
        sa.Column("sell_currency", sa.String(length=3), nullable=False),
        sa.Column("operation_direction", sa.String(length=10), nullable=False),
        sa.Column("counterparty_id", sa.String(length=20), sa.ForeignKey("counterparty.id"), nullable=False),
        sa.Column("deal_type_id", sa.Integer(), sa.ForeignKey("deal_type.id"), nullable=False),
        sa.Column("deal_state_id", sa.Integer(), sa.ForeignKey("deal_state.id"), nullable=False),
        sa.Column("validation_status_id", sa.Integer(), sa.ForeignKey("validation_status.id"), nullable=False),
        sa.Column("trader_id", sa.String(length=36), nullable=False),
        sa.Column("trader_email", sa.String(length=320), nullable=False),
        sa.Column("positioner_id", sa.String(length=36)),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_fx_deal_trade_date", "fx_deal", ["trade_date"])
    op.create_index("ix_fx_deal_counterparty_id", "fx_deal", ["counterparty_id"])
    op.create_index("ix_fx_deal_deal_state_id", "fx_deal", ["deal_state_id"])

    op.create_table(
        "payment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fx_deal.id", ondelete="CASCADE")),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency_code", sa.String(length=3), sa.ForeignKey("currency.code"), nullable=False),
        sa.Column("account_code", sa.String(length=30)),
        sa.Column("payment_direction_id", sa.Integer(), sa.ForeignKey("payment_direction.id"), nullable=False),
        sa.Column("value_date", sa.Date()),
    )
    op.create_table(
        "positioner_solution",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fx_deal.id", ondelete="CASCADE"), unique=True),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("positioner_id", sa.String(length=36), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "audit_log_entry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
    )
    op.create_index("ix_audit_log_entry_entity_id", "audit_log_entry", ["entity_id"])

    _seed_lookup_data()


def _seed_lookup_data() -> None:
    deal_state = sa.table("deal_state", sa.column("id"), sa.column("code"))
    deal_type = sa.table("deal_type", sa.column("id"), sa.column("code"))
    payment_direction = sa.table("payment_direction", sa.column("id"), sa.column("code"))
    validation_status = sa.table("validation_status", sa.column("id"), sa.column("code"))
    currency = sa.table(
        "currency",
        sa.column("code"),
        sa.column("name"),
        sa.column("decimal_places"),
    )
    counterparty = sa.table(
        "counterparty",
        sa.column("id"),
        sa.column("name"),
        sa.column("bic"),
        sa.column("country"),
        sa.column("is_active"),
    )
    nostro = sa.table(
        "nostro_account",
        sa.column("id"),
        sa.column("currency_code"),
        sa.column("bank_name"),
        sa.column("account_number"),
        sa.column("is_active"),
    )
    calendar = sa.table(
        "business_calendar",
        sa.column("calendar_date"),
        sa.column("is_business_day"),
    )

    op.bulk_insert(
        deal_state,
        [
            {"id": 1, "code": "DRAFT"},
            {"id": 2, "code": "WAITING_FOR_POSITIONER"},
            {"id": 3, "code": "APPROVED"},
            {"id": 4, "code": "REJECTED"},
        ],
    )
    op.bulk_insert(
        deal_type,
        [
            {"id": 1, "code": "TOD"},
            {"id": 2, "code": "TOM"},
            {"id": 3, "code": "SPOT"},
            {"id": 4, "code": "FORWARD"},
        ],
    )
    op.bulk_insert(
        payment_direction,
        [{"id": 1, "code": "IN"}, {"id": 2, "code": "OUT"}],
    )
    op.bulk_insert(
        validation_status,
        [
            {"id": 1, "code": "NOT_VALIDATED"},
            {"id": 2, "code": "VALID"},
            {"id": 3, "code": "INVALID"},
        ],
    )
    op.bulk_insert(
        currency,
        [
            {"code": "RUB", "name": "Russian Ruble", "decimal_places": 2},
            {"code": "USD", "name": "US Dollar", "decimal_places": 2},
            {"code": "EUR", "name": "Euro", "decimal_places": 2},
            {"code": "CNY", "name": "Chinese Yuan", "decimal_places": 2},
            {"code": "GBP", "name": "British Pound", "decimal_places": 2},
            {"code": "CHF", "name": "Swiss Franc", "decimal_places": 2},
        ],
    )
    op.bulk_insert(
        counterparty,
        [
            {"id": "SBER", "name": "ПАО Сбербанк", "bic": "SABRRUMM", "country": "RU", "is_active": True},
            {"id": "VTBR", "name": "ПАО Банк ВТБ", "bic": "VTBRRUMM", "country": "RU", "is_active": True},
            {"id": "GAZP", "name": "АО Газпромбанк", "bic": "GAZPRUMM", "country": "RU", "is_active": True},
            {"id": "RAIF", "name": "АО Райффайзенбанк", "bic": "RZBMRUMM", "country": "RU", "is_active": True},
            {"id": "TBRF", "name": "АО ТБанк", "bic": "TICSRUMM", "country": "RU", "is_active": True},
            {"id": "OPEN", "name": "ПАО Банк Открытие", "bic": "JSNMRUMM", "country": "RU", "is_active": True},
            {"id": "ALFA", "name": "АО Альфа-Банк", "bic": "ALFARUMM", "country": "RU", "is_active": True},
            {"id": "MKB", "name": "ПАО Московский Кредитный Банк", "bic": "MCRBRUMM", "country": "RU", "is_active": True},
            {"id": "ICBC", "name": "ICBC Moscow", "bic": "ICBKRUMM", "country": "RU", "is_active": True},
            {"id": "INACTIVE", "name": "Inactive Test CP", "bic": "INACRUMM", "country": "RU", "is_active": False},
        ],
    )
    op.bulk_insert(
        nostro,
        [
            {"id": "NOS-USD-001", "currency_code": "USD", "bank_name": "Citi NA", "account_number": "363000001", "is_active": True},
            {"id": "NOS-EUR-001", "currency_code": "EUR", "bank_name": "Deutsche Bank", "account_number": "363000002", "is_active": True},
            {"id": "NOS-RUB-001", "currency_code": "RUB", "bank_name": "АСУБАНК Nostro RUB", "account_number": "40702810000000000001", "is_active": True},
            {"id": "NOS-CNY-001", "currency_code": "CNY", "bank_name": "BOC Hong Kong", "account_number": "363000003", "is_active": True},
        ],
    )

    calendar_rows = []
    for day in range(1, 32):
        is_business = day not in (3, 4, 10, 11, 17, 18, 24, 25, 31)
        calendar_rows.append({"calendar_date": date(2026, 5, day), "is_business_day": is_business})
    for day in range(1, 8):
        calendar_rows.append({"calendar_date": date(2026, 6, day), "is_business_day": day not in (6, 7)})
    op.bulk_insert(calendar, calendar_rows)


def downgrade() -> None:
    op.drop_table("audit_log_entry")
    op.drop_table("positioner_solution")
    op.drop_table("payment")
    op.drop_table("fx_deal")
    op.drop_table("business_calendar")
    op.drop_table("nostro_account")
    op.drop_table("counterparty")
    op.drop_table("currency")
    op.drop_table("validation_status")
    op.drop_table("payment_direction")
    op.drop_table("deal_type")
    op.drop_table("deal_state")
