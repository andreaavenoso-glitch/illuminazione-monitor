"""service_status: live state of Claude (credit / limit), to show warnings only while they hold

Revision ID: 0018_service_status
Revises: 0017_referenti_freshness
Create Date: 2026-11-23 15:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_service_status"
down_revision: str | None = "0017_referenti_freshness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_status",
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("ok", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("service_status")
