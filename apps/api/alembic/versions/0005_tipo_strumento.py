"""add tipo_strumento to procurement_records

Revision ID: 0005_tipo_strumento
Revises: 0004_users
Create Date: 2026-07-03 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_tipo_strumento"
down_revision: str | None = "0004_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "procurement_records",
        sa.Column("tipo_strumento", sa.String, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("procurement_records", "tipo_strumento")
