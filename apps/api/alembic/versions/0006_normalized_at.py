"""add normalized_at to raw_records

Revision ID: 0006_normalized_at
Revises: 0005_tipo_strumento
Create Date: 2026-07-09 09:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_normalized_at"
down_revision: str | None = "0005_tipo_strumento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "raw_records",
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("raw_records", "normalized_at")
