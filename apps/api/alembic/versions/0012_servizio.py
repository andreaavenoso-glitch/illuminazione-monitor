"""procurement_records.servizio (which services of the catalog a notice is about)

Revision ID: 0012_servizio
Revises: 0011_source_discovered
Create Date: 2026-11-18 20:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_servizio"
down_revision: str | None = "0011_source_discovered"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("procurement_records", sa.Column("servizio", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("procurement_records", "servizio")
