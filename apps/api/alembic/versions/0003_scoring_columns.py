"""scoring columns: score_commerciale, priorita_commerciale, dedup_key

Revision ID: 0003_scoring_columns
Revises: 0002_core_tables
Create Date: 2026-04-22 19:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_scoring_columns"
down_revision: str | None = "0002_core_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "procurement_records",
        sa.Column("score_commerciale", sa.Integer, nullable=True),
    )
    op.add_column(
        "procurement_records",
        sa.Column("priorita_commerciale", sa.String, nullable=True),
    )
    op.add_column(
        "procurement_records",
        sa.Column("dedup_key", sa.String, nullable=True),
    )
    op.create_index(
        "ix_procurement_dedup_key", "procurement_records", ["dedup_key"]
    )
    op.create_index(
        "ix_procurement_priorita", "procurement_records", ["priorita_commerciale"]
    )


def downgrade() -> None:
    op.drop_index("ix_procurement_priorita", table_name="procurement_records")
    op.drop_index("ix_procurement_dedup_key", table_name="procurement_records")
    op.drop_column("procurement_records", "dedup_key")
    op.drop_column("procurement_records", "priorita_commerciale")
    op.drop_column("procurement_records", "score_commerciale")
