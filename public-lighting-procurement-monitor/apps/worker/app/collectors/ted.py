from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from parsing_rules import CPV_LIGHTING_CODES

from app.collectors.base import BaseCollector, CollectorError, RawRecordDraft


class TEDCollector(BaseCollector):
    """TED (Tenders Electronic Daily) collector.

    Uses the TED REST v3 search endpoint. Filters for Italian notices whose
    CPV codes fall within the public-lighting vocabulary (see
    parsing_rules.regex.CPV_LIGHTING_CODES).
    """

    name = "ted"
    DEFAULT_ENDPOINT = "https://ted.europa.eu/api/v3.0/notices/search"
    MAX_RESULTS = 50

    async def fetch(self, *, since: datetime | None = None) -> list[RawRecordDraft]:
        lookback = since or (datetime.now(tz=UTC) - timedelta(days=7))
        from_date = lookback.strftime("%Y%m%d")

        cpv_clause = " OR ".join(f"CPV={c}" for c in sorted(CPV_LIGHTING_CODES))
        query = f"(CY=IT) AND PD>={from_date} AND ({cpv_clause})"

        payload: dict[str, Any] = {
            "query": query,
            "page": 1,
            "limit": self.MAX_RESULTS,
            "scope": 3,
            "fields": [
                "ND", "PD", "TI", "CY", "AA", "BC", "NC", "links",
                "notice-type", "procurement-method", "deadline-receipt-tender-date-lot",
                "total-value", "value-lot", "buyer-name-1", "buyer-city-1",
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(self.DEFAULT_ENDPOINT, json=payload)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise CollectorError(f"TED request failed: {exc}") from exc

            try:
                data = response.json()
            except ValueError as exc:
                raise CollectorError(f"TED returned invalid JSON: {exc}") from exc

        notices = data.get("notices") or data.get("results") or []
        drafts: list[RawRecordDraft] = []
        for notice in notices:
            link = _first_link(notice.get("links") or [])
            title = _first_value(notice.get("TI")) or notice.get("title")
            raw_date = _parse_ted_date(notice.get("PD"))
            if not link:
                nd = notice.get("ND")
                if nd:
                    link = f"https://ted.europa.eu/udl?uri=TED:NOTICE:{nd}"
            if not link:
                continue
            drafts.append(
                RawRecordDraft(
                    raw_url=link,
                    raw_title=title,
                    raw_body=_notice_summary(notice),
                    raw_date=raw_date,
                    extracted={"notice": notice, "source": "ted"},
                )
            )
        return drafts


def _first_link(links: list[Any]) -> str | None:
    for entry in links:
        if isinstance(entry, dict):
            url = entry.get("href") or entry.get("url")
            if url:
                return url
        elif isinstance(entry, str):
            return entry
    return None


def _first_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        for v in value:
            if isinstance(v, dict):
                for candidate in ("text", "value", "content"):
                    if candidate in v:
                        return str(v[candidate])
            elif isinstance(v, str):
                return v
        return None
    if isinstance(value, dict):
        for candidate in ("text", "value", "content"):
            if candidate in value:
                return str(value[candidate])
        return None
    return str(value)


def _parse_ted_date(raw: Any) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw), "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _notice_summary(notice: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "TI", "title", "notice-type", "procurement-method", "buyer-name-1",
        "buyer-city-1", "total-value", "CY",
    ):
        value = notice.get(key)
        flat = _first_value(value)
        if flat:
            parts.append(f"{key}: {flat}")
    return " | ".join(parts)
