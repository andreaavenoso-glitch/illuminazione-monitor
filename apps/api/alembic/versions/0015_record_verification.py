"""procurement_records: automatic verification of gare / manifestazioni

Revision ID: 0015_record_verification
Revises: 0014_api_usage
Create Date: 2026-11-22 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_record_verification"
down_revision: str | None = "0014_api_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("procurement_records", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("procurement_records", sa.Column("verifica_esito", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("procurement_records", "verifica_esito")
    op.drop_column("procurement_records", "verified_at")
