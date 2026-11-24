"""entities.pec (from IPA) and ricerche_referenti (checklist of the referenti search)

Revision ID: 0019_ricerca_referenti
Revises: 0018_service_status
Create Date: 2026-11-23 18:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_ricerca_referenti"
down_revision: str | None = "0018_service_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("entities", sa.Column("pec", sa.String, nullable=True))
    op.create_table(
        "ricerche_referenti",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ente", sa.String, nullable=False),
        sa.Column("regione", sa.String, nullable=True),
        sa.Column("metodo", sa.String, nullable=False, server_default="script"),
        sa.Column("checklist", postgresql.JSONB, nullable=True),
        sa.Column("lacune", postgresql.JSONB, nullable=True),
        sa.Column("stampa", sa.Text, nullable=True),
        sa.Column("elezione_data", sa.Date, nullable=True),
        sa.Column("mandato_scadenza", sa.Date, nullable=True),
        sa.Column("eseguita_il", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ente", "regione", name="uq_ricerca_referenti"),
    )
    op.create_index("ix_ricerche_referenti_ente", "ricerche_referenti", ["ente"])


def downgrade() -> None:
    op.drop_table("ricerche_referenti")
    op.drop_column("entities", "pec")
