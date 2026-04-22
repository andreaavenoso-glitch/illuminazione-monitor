"""core tables (sources, entities, watchlist_items, raw_records, procurement_records,
record_events, alerts, documents, daily_reports, job_runs)

Revision ID: 0002_core_tables
Revises: 0001_baseline
Create Date: 2026-04-22 08:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_core_tables"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("source_type", sa.String, nullable=False),
        sa.Column("platform_type", sa.String, nullable=True),
        sa.Column("base_url", sa.String, nullable=False),
        sa.Column("sector_scope", sa.String, nullable=True),
        sa.Column("priority", sa.String, nullable=False, server_default="B"),
        sa.Column("frequency", sa.String, nullable=False, server_default="daily"),
        sa.Column("reliability_score", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("productivity_score", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("publication_model", sa.String, nullable=True),
        sa.Column("source_priority_rank", sa.Integer, nullable=False, server_default="999"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sources_active", "sources", ["active"])

    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("entity_type", sa.String, nullable=True),
        sa.Column("region", sa.String, nullable=True),
        sa.Column("province", sa.String, nullable=True),
        sa.Column("municipality", sa.String, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", "region", name="uq_entities_name_region"),
    )
    op.create_index("ix_entities_region", "entities", ["region"])

    op.create_table(
        "watchlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("url_gare", sa.String, nullable=True),
        sa.Column("url_esiti", sa.String, nullable=True),
        sa.Column("url_albo", sa.String, nullable=True),
        sa.Column("url_trasparenza", sa.String, nullable=True),
        sa.Column("url_determine", sa.String, nullable=True),
        sa.Column("frequency", sa.String, nullable=False, server_default="daily"),
        sa.Column("priority", sa.String, nullable=False, server_default="B"),
        sa.Column("reliability_score", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("productivity_score", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("publication_model", sa.String, nullable=True),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_watchlist_active", "watchlist_items", ["active"])

    op.create_table(
        "raw_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_title", sa.Text, nullable=True),
        sa.Column("raw_body", sa.Text, nullable=True),
        sa.Column("raw_html", sa.Text, nullable=True),
        sa.Column("raw_url", sa.String, nullable=False),
        sa.Column("raw_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extracted_json", postgresql.JSONB, nullable=True),
        sa.Column("checksum", sa.String, nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_raw_records_checksum", "raw_records", ["checksum"])
    op.create_index("ix_raw_records_source", "raw_records", ["source_id"])
    op.execute("CREATE INDEX ix_raw_records_extracted_json ON raw_records USING GIN (extracted_json)")

    op.create_table(
        "procurement_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String, nullable=True),
        sa.Column("source_priority_rank", sa.Integer, nullable=False, server_default="999"),
        sa.Column("numero_gara_id", sa.String, nullable=True),
        sa.Column("data_pubblicazione", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tipo_appalto", sa.String, nullable=True),
        sa.Column("descrizione", sa.Text, nullable=True),
        sa.Column("ente", sa.String, nullable=False),
        sa.Column("importo", sa.Numeric(18, 2), nullable=True),
        sa.Column("provincia", sa.String, nullable=True),
        sa.Column("regione", sa.String, nullable=True),
        sa.Column("comune", sa.String, nullable=True),
        sa.Column("area_text", sa.Text, nullable=True),
        sa.Column("tipologia_gara_procedura", sa.String, nullable=True),
        sa.Column("scadenza", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criterio", sa.String, nullable=True),
        sa.Column("cig", sa.String, nullable=True),
        sa.Column("classifiche", sa.Text, nullable=True),
        sa.Column("link_bando", sa.String, nullable=False),
        sa.Column("macrosettore", sa.String, nullable=False, server_default="Illuminazione pubblica"),
        sa.Column("stato_procedurale", sa.String, nullable=False),
        sa.Column("tipo_novita", sa.String, nullable=False),
        sa.Column("flag_concessione_ambito", sa.String, nullable=False, server_default="No"),
        sa.Column("flag_ppp_doppio_oggetto", sa.String, nullable=False, server_default="No"),
        sa.Column("flag_in_house_ambito", sa.String, nullable=False, server_default="No"),
        sa.Column("flag_om", sa.String, nullable=False, server_default="No"),
        sa.Column("flag_pre_gara", sa.String, nullable=False, server_default="No"),
        sa.Column("tag_tecnico", sa.Text, nullable=True),
        sa.Column("validation_level", sa.String, nullable=True),
        sa.Column("reliability_index", sa.String, nullable=True),
        sa.Column("is_weak_evidence", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("master_record_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("procurement_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_procurement_cig", "procurement_records", ["cig"])
    op.create_index("ix_procurement_external_id", "procurement_records", ["external_id"])
    op.create_index("ix_procurement_master", "procurement_records", ["master_record_id"])
    op.create_index("ix_procurement_ente_regione", "procurement_records", ["ente", "regione"])
    op.create_index("ix_procurement_stato", "procurement_records", ["stato_procedurale"])

    op.create_table(
        "record_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("procurement_record_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("procurement_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_url", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_record_events_pr", "record_events", ["procurement_record_id"])

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("procurement_record_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("procurement_records.id", ondelete="CASCADE"), nullable=True),
        sa.Column("alert_type", sa.String, nullable=False),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("is_open", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_record", "alerts", ["procurement_record_id"])
    op.create_index("ix_alerts_open", "alerts", ["is_open"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("procurement_record_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("procurement_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String, nullable=True),
        sa.Column("mime_type", sa.String, nullable=True),
        sa.Column("storage_url", sa.String, nullable=False),
        sa.Column("text_content", sa.Text, nullable=True),
        sa.Column("checksum", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_pr", "documents", ["procurement_record_id"])
    op.create_index("ix_documents_checksum", "documents", ["checksum"])

    op.create_table(
        "daily_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_date", sa.Date, nullable=False, unique=True),
        sa.Column("total_new", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_updates", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_pregara", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_new_sources", sa.Integer, nullable=False, server_default="0"),
        sa.Column("report_json", postgresql.JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_name", sa.String, nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_valid", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_weak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duplicates_removed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_job_runs_name", "job_runs", ["job_name"])
    op.create_index("ix_job_runs_started", "job_runs", ["started_at"])


def downgrade() -> None:
    op.drop_table("job_runs")
    op.drop_table("daily_reports")
    op.drop_table("documents")
    op.drop_table("alerts")
    op.drop_table("record_events")
    op.drop_table("procurement_records")
    op.drop_table("raw_records")
    op.drop_table("watchlist_items")
    op.drop_table("entities")
    op.drop_table("sources")
