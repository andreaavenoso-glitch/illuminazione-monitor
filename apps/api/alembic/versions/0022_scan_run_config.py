"""scan_runs.config: the settings of each run, to compare runs (history)

Revision ID: 0022_scan_run_config
Revises: 0021_scan_stop
Create Date: 2026-11-24 09:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_scan_run_config"
down_revision: str | None = "0021_scan_stop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scan_runs", sa.Column("config", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("scan_runs", "config")
