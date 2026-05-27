"""Add deal limits and test counterparty for regulatory NSI checks.

Revision ID: 005
Revises: 004
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deal_limit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("counterparty_id", sa.String(length=20), sa.ForeignKey("counterparty.id"), nullable=True),
        sa.Column("currency_code", sa.String(length=3), sa.ForeignKey("currency.code"), nullable=True),
        sa.Column("max_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_deal_limit_counterparty_id", "deal_limit", ["counterparty_id"])
    op.create_index("ix_deal_limit_currency_code", "deal_limit", ["currency_code"])

    deal_limit = sa.table(
        "deal_limit",
        sa.column("id"),
        sa.column("counterparty_id"),
        sa.column("currency_code"),
        sa.column("max_amount"),
        sa.column("is_active"),
    )
    counterparty = sa.table(
        "counterparty",
        sa.column("id"),
        sa.column("name"),
        sa.column("bic"),
        sa.column("country"),
        sa.column("is_active"),
    )

    op.bulk_insert(
        deal_limit,
        [
            {
                "id": 1,
                "counterparty_id": "VTBR",
                "currency_code": "USD",
                "max_amount": "10000000.00",
                "is_active": True,
            },
            {
                "id": 2,
                "counterparty_id": None,
                "currency_code": "USD",
                "max_amount": "50000000.00",
                "is_active": True,
            },
        ],
    )
    op.bulk_insert(
        counterparty,
        [
            {
                "id": "NOBIC",
                "name": "Test Counterparty Without BIC",
                "bic": None,
                "country": "RU",
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM counterparty WHERE id = 'NOBIC'"))
    op.drop_index("ix_deal_limit_currency_code", table_name="deal_limit")
    op.drop_index("ix_deal_limit_counterparty_id", table_name="deal_limit")
    op.drop_table("deal_limit")
