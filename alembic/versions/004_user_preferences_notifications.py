"""Add user preferences and notification read state.

Revision ID: 004
Revises: 003
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_preference",
        sa.Column("user_id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("department", sa.String(length=120), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "user_notification_state",
        sa.Column("user_id", sa.String(length=36), primary_key=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_notification_state")
    op.drop_table("user_preference")
