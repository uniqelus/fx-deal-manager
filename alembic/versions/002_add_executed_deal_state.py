"""Add EXECUTED deal state for position system integration.

Revision ID: 002
Revises: 001
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO deal_state (id, code) SELECT 5, 'EXECUTED' "
        "WHERE NOT EXISTS (SELECT 1 FROM deal_state WHERE code = 'EXECUTED')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM deal_state WHERE code = 'EXECUTED'")
