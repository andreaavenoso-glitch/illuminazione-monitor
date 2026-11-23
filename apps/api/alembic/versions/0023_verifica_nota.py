"""procurement_records.verifica_nota: what the deadline hunt tried

Revision ID: 0023_verifica_nota
Revises: 0022_scan_run_config
Create Date: 2026-11-24 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_verifica_nota"
down_revision: str | None = "0022_scan_run_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("procurement_records", sa.Column("verifica_nota", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("procurement_records", "verifica_nota")
