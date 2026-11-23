"""analisi_record: preliminary analysis of the documentation of a notice

Revision ID: 0020_analisi_record
Revises: 0019_ricerca_referenti
Create Date: 2026-11-23 20:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_analisi_record"
down_revision: str | None = "0019_ricerca_referenti"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analisi_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "procurement_record_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("procurement_records.id", ondelete="CASCADE"), nullable=False, unique=True,
        ),
        sa.Column("documenti", postgresql.JSONB, nullable=True),
        sa.Column("campi", postgresql.JSONB, nullable=True),
        sa.Column("metodo", sa.String, nullable=False, server_default="regole"),
        sa.Column("eseguita_il", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("analisi_record")
