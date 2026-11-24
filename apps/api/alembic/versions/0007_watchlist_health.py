"""add source health columns to watchlist_items

Revision ID: 0007_watchlist_health
Revises: 0006_normalized_at
Create Date: 2026-11-18 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_watchlist_health"
down_revision: str | None = "0006_normalized_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "watchlist_items",
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "watchlist_items",
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column("watchlist_items", sa.Column("last_error", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("watchlist_items", "last_error")
    op.drop_column("watchlist_items", "consecutive_failures")
    op.drop_column("watchlist_items", "last_success_at")
