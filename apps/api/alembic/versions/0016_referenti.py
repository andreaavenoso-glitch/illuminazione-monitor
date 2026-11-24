"""referenti: political and technical contacts of the enti, with their source

Revision ID: 0016_referenti
Revises: 0015_record_verification
Create Date: 2026-11-22 15:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_referenti"
down_revision: str | None = "0015_record_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "referenti",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ente", sa.String, nullable=False),
        sa.Column("regione", sa.String, nullable=True),
        sa.Column("nome", sa.String, nullable=False),
        sa.Column("ruolo", sa.String, nullable=False),
        sa.Column("qualifica", sa.String, nullable=True),
        sa.Column("email", sa.String, nullable=True),
        sa.Column("telefono", sa.String, nullable=True),
        sa.Column("fonte_url", sa.String, nullable=False),
        sa.Column("citazione", sa.Text, nullable=True),
        sa.Column("stato", sa.String, nullable=False, server_default="da_confermare"),
        sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ente", "regione", "ruolo", "nome", name="uq_referente"),
    )
    op.create_index("ix_referenti_ente", "referenti", ["ente"])
    op.create_index("ix_referenti_regione", "referenti", ["regione"])


def downgrade() -> None:
    op.drop_table("referenti")
