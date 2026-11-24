"""sources.discovered_from (regional sites found while crawling comuni)

Revision ID: 0011_source_discovered
Revises: 0010_content_hashes
Create Date: 2026-11-18 19:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_source_discovered"
down_revision: str | None = "0010_content_hashes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("discovered_from", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "discovered_from")
