"""Dedicated TED (Tenders Electronic Daily, EU) collector.

TED exposes a real JSON REST API (POST /v3/notices/search) — no HTML
scraping or LLM parsing needed. We query by CPV code + buyer country +
publication-date range and convert results directly into
RawRecordDrafts.

API shape confirmed by hand:
    POST https://api.ted.europa.eu/v3/notices/search
    {"query": "classification-cpv=X AND buyer-country=ITA AND publication-date>=YYYYMMDD",
     "fields": [...], "limit": N}
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

import httpx
from app.collectors.base import BaseCollector, CollectorResult, RawRecordDraft
from shared_models import RawRecord
from sqlalchemy.ext.asyncio import AsyncSession

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

LIGHTING_CPV_CODES = ["34928510", "34993000", "50232000", "45316110"]

FIELDS = ["publication-number", "notice-title", "buyer-name", "publication-date", "links"]


def _pick_lang(field: dict | None, *, prefer: tuple[str, ...] = ("ita", "eng")) -> str | None:
    if not field:
        return None
    for lang in prefer:
        if lang in field:
            value = field[lang]
            return value[0] if isinstance(value, list) else value
    for value in field.values():
        return value[0] if isinstance(value, list) else value
    return None


class TEDCollector(BaseCollector):
    name: ClassVar[str] = "ted"

    async def fetch(self, *, since: datetime | None = None) -> list[RawRecordDraft]:
        since = since or (datetime.now(tz=UTC) - timedelta(days=14))
        date_filter = since.strftime("%Y%m%d")
        cpv_clause = " OR ".join(f"classification-cpv={code}" for code in LIGHTING_CPV_CODES)
        query = f"({cpv_clause}) AND buyer-country=ITA AND publication-date>={date_filter}"

        async with httpx.AsyncClient(timeout=self.timeout) as http:
            try:
                resp = await http.post(
                    TED_SEARCH_URL,
                    json={"query": query, "fields": FIELDS, "limit": 50},
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                return []

        drafts: list[RawRecordDraft] = []
        for notice in data.get("notices", []):
            title = _pick_lang(notice.get("notice-title")) or "Bando TED senza titolo"
            buyer = _pick_lang(notice.get("buyer-name"))
            pub_number = notice.get("publication-number", "")
            raw_date: datetime | None = None
            pub_date = notice.get("publication-date")
            if pub_date:
                try:
                    raw_date = datetime.fromisoformat(str(pub_date)[:10]).replace(tzinfo=UTC)
                except ValueError:
                    raw_date = None

            html_links = (notice.get("links") or {}).get("htmlDirect") or {}
            url = html_links.get("ITA") or html_links.get("ENG") or (
                f"https://ted.europa.eu/en/notice/{pub_number}/html" if pub_number else TED_SEARCH_URL
            )

            body_parts = [f"Ente: {buyer}"] if buyer else []
            body_parts.append(f"Numero pubblicazione TED: {pub_number}")
            drafts.append(
                RawRecordDraft(
                    raw_url=url,
                    raw_title=title,
                    raw_body="; ".join(body_parts),
                    raw_html=None,
                    raw_date=raw_date,
                    extracted={
                        "ente": buyer,
                        "publication_number": pub_number,
                        "extracted_by": "ted-api-direct",
                        "perimeter_prevalidated": True,
                    },
                )
            )
        return drafts

    async def persist(
        self,
        session: AsyncSession,
        drafts: list[RawRecordDraft],
    ) -> CollectorResult:
        # Skip the keyword-perimeter filter — the TED query already scopes
        # results to lighting CPV codes, and notice titles are terse
        # machine translations that often miss the exact keyword phrases.
        result = CollectorResult(found=len(drafts))
        seen: set[str] = set()
        for draft in drafts:
            checksum = draft.checksum()
            if checksum in seen:
                result.duplicates_removed += 1
                continue
            seen.add(checksum)
            session.add(
                RawRecord(
                    source_id=self.source_id,
                    raw_title=draft.raw_title,
                    raw_body=draft.raw_body,
                    raw_html=draft.raw_html,
                    raw_url=draft.raw_url,
                    raw_date=draft.raw_date or datetime.now(tz=UTC),
                    extracted_json=draft.extracted or None,
                    checksum=checksum,
                )
            )
            result.valid += 1
        return result
