"""referenti: date of the source page, last election, reason when to be confirmed

Revision ID: 0017_referenti_freshness
Revises: 0016_referenti
Create Date: 2026-11-23 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_referenti_freshness"
down_revision: str | None = "0016_referenti"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("referenti", sa.Column("data_fonte", sa.Date, nullable=True))
    op.add_column("referenti", sa.Column("elezione_data", sa.Date, nullable=True))
    op.add_column("referenti", sa.Column("motivo", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("referenti", "motivo")
    op.drop_column("referenti", "elezione_data")
    op.drop_column("referenti", "data_fonte")
