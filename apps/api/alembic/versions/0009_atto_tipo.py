"""procurement_records.atto_tipo (Claude's label for pre-tender acts)

Revision ID: 0009_atto_tipo
Revises: 0008_regions
Create Date: 2026-11-18 17:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_atto_tipo"
down_revision: str | None = "0008_regions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("procurement_records", sa.Column("atto_tipo", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("procurement_records", "atto_tipo")
