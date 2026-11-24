"""lavorazioni (selection of the notices to pursue) and the depth of the documentation analysis

Revision ID: 0024_lavorazioni
Revises: 0023_verifica_nota
Create Date: 2026-11-24 15:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_lavorazioni"
down_revision: str | None = "0023_verifica_nota"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analisi_record", sa.Column("profondita", sa.String, nullable=False, server_default="base"))
    op.create_table(
        "lavorazioni",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("procurement_record_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("procurement_records.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("stato", sa.String, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("decisa_il", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("email_il", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sintesi_il", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lavorazioni")
    op.drop_column("analisi_record", "profondita")
