"""scan_runs.stop_requested: stop a running collection from the page

Revision ID: 0021_scan_stop
Revises: 0020_analisi_record
Create Date: 2026-11-23 22:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_scan_stop"
down_revision: str | None = "0020_analisi_record"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scan_runs", sa.Column("stop_requested", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("scan_runs", "stop_requested")
