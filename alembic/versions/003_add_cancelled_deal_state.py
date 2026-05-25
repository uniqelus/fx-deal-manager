"""Add CANCELLED deal state for FR-015 (trader-initiated cancellation in DRAFT).

Revision ID: 003
Revises: 002
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO deal_state (id, code) SELECT 6, 'CANCELLED' "
        "WHERE NOT EXISTS (SELECT 1 FROM deal_state WHERE code = 'CANCELLED')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM deal_state WHERE code = 'CANCELLED'")
