from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RawRecordPayload(BaseModel):
    """Normalized payload a collector produces, before persisting to raw_records."""

    model_config = ConfigDict(extra="allow")

    source_id: str
    raw_title: str | None = None
    raw_body: str | None = None
    raw_html: str | None = None
    raw_url: str
    raw_date: datetime | None = None
    extracted: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None


class ExtractedFields(BaseModel):
    """Fields a parser may extract from raw text (Sprint 5+)."""

    ente: str | None = None
    descrizione: str | None = None
    importo: Decimal | None = None
    cig: str | None = None
    cup: str | None = None
    cpv: list[str] = Field(default_factory=list)
    scadenza: datetime | None = None
    data_pubblicazione: datetime | None = None
    procedura: str | None = None
    regione: str | None = None
    provincia: str | None = None
    link_bando: str | None = None


__all__ = ["ExtractedFields", "RawRecordPayload"]
