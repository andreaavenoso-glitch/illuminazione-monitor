"""scan_runs and scan_items: per-comune progress of a scan

Revision ID: 0013_scan_runs
Revises: 0012_servizio
Create Date: 2026-11-18 21:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_scan_runs"
down_revision: str | None = "0012_servizio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("region", sa.String, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="running"),
        sa.Column("sample_limit", sa.Integer, nullable=True),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("claude_status", sa.String, nullable=False, server_default="unused"),
        sa.Column("claude_error", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("ix_scan_runs_region", "scan_runs", ["region"])
    op.create_table(
        "scan_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("watchlist_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ente", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pages_read", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pages_skipped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("claude_calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("claude_errors", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("deepest", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stopped_by", sa.String, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("ix_scan_items_run_id", "scan_items", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_items_run_id", table_name="scan_items")
    op.drop_table("scan_items")
    op.drop_index("ix_scan_runs_region", table_name="scan_runs")
    op.drop_table("scan_runs")
