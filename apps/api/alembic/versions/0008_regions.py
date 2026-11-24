"""regional structure: region_settings, notified_at, sources.regione/ruolo

Revision ID: 0008_regions
Revises: 0007_watchlist_health
Create Date: 2026-11-18 15:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_regions"
down_revision: str | None = "0007_watchlist_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "region_settings",
        sa.Column("region", sa.String, primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("recipients", sa.Text, nullable=True),
        sa.Column("last_digest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("procurement_records", sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("regione", sa.String, nullable=True))
    op.add_column("sources", sa.Column("ruolo", sa.String, nullable=True))
    op.create_index("ix_sources_regione", "sources", ["regione"])


def downgrade() -> None:
    op.drop_index("ix_sources_regione", table_name="sources")
    op.drop_column("sources", "ruolo")
    op.drop_column("sources", "regione")
    op.drop_column("procurement_records", "notified_at")
    op.drop_table("region_settings")
