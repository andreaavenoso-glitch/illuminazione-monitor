"""watchlist_items.pc_letto_il / pc_esito: report of the reading made from the user's PC

Revision ID: 0026_watchlist_pc
Revises: 0025_categoria_analisi
Create Date: 2026-11-24 19:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_watchlist_pc"
down_revision: str | None = "0025_categoria_analisi"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("watchlist_items", sa.Column("pc_letto_il", sa.DateTime(timezone=True), nullable=True))
    op.add_column("watchlist_items", sa.Column("pc_esito", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("watchlist_items", "pc_esito")
    op.drop_column("watchlist_items", "pc_letto_il")
