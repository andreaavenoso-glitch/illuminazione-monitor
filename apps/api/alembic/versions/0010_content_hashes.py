"""watchlist_items.content_hashes (skip pages unchanged since the last analysis)

Revision ID: 0010_content_hashes
Revises: 0009_atto_tipo
Create Date: 2026-11-18 18:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_content_hashes"
down_revision: str | None = "0009_atto_tipo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("watchlist_items", sa.Column("content_hashes", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("watchlist_items", "content_hashes")
