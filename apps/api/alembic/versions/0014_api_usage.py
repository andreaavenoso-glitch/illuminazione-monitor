"""api_usage: tokens and estimated cost of every Anthropic API call

Revision ID: 0014_api_usage
Revises: 0013_scan_runs
Create Date: 2026-11-18 22:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_api_usage"
down_revision: str | None = "0013_scan_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("purpose", sa.String, nullable=False),
        sa.Column("label", sa.String, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scan_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scan_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scan_items.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_api_usage_created_at", "api_usage", ["created_at"])
    op.create_index("ix_api_usage_run_id", "api_usage", ["run_id"])
    op.create_index("ix_api_usage_scan_item_id", "api_usage", ["scan_item_id"])


def downgrade() -> None:
    op.drop_index("ix_api_usage_scan_item_id", table_name="api_usage")
    op.drop_index("ix_api_usage_run_id", table_name="api_usage")
    op.drop_index("ix_api_usage_created_at", table_name="api_usage")
    op.drop_table("api_usage")
