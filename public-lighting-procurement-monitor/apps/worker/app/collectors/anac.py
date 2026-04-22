from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.collectors.base import BaseCollector, CollectorError, RawRecordDraft


class ANACCollector(BaseCollector):
    """ANAC BDNCP collector.

    Uses the open-data CKAN-style API exposed at https://dati.anticorruzione.it.
    Public lighting notices tend to surface in datasets like `bandi-cig-modalita-realizzazione`
    and `appalti-in-corso`. We keep the dataset id configurable via the source `base_url`
    (which should include the query path, e.g. /opendata/ds-bandi-cig).
    """

    name = "anac"
    DEFAULT_LIMIT = 100

    async def fetch(self, *, since: datetime | None = None) -> list[RawRecordDraft]:
        lookback = since or (datetime.now(tz=UTC) - timedelta(days=14))

        endpoint = self._endpoint()
        params = {
            "q": "illuminazione pubblica OR pubblica illuminazione OR relamping",
            "rows": self.DEFAULT_LIMIT,
            "sort": "data_pubblicazione desc",
            "fq": f"data_pubblicazione:[{lookback.strftime('%Y-%m-%d')}T00:00:00Z TO *]",
        }

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                raise CollectorError(f"ANAC request failed: {exc}") from exc
            except ValueError as exc:
                raise CollectorError(f"ANAC returned invalid JSON: {exc}") from exc

        records = _extract_records(data)
        drafts: list[RawRecordDraft] = []
        for rec in records:
            link = _pick(rec, "link_bando", "url", "link", "url_bando")
            if not link:
                continue
            drafts.append(
                RawRecordDraft(
                    raw_url=link,
                    raw_title=_pick(rec, "oggetto", "oggetto_principale_contratto", "titolo"),
                    raw_body=_flatten(rec),
                    raw_date=_parse_iso(_pick(rec, "data_pubblicazione", "data_pubb", "data_inizio")),
                    extracted={"record": rec, "source": "anac"},
                )
            )
        return drafts

    def _endpoint(self) -> str:
        if "/opendata" in self.base_url or "api" in self.base_url:
            return self.base_url
        return f"{self.base_url}/opendata/datastore/search"


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    # CKAN-ish shapes
    for key in ("records", "results", "data"):
        val = payload.get(key)
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
    result = payload.get("result")
    if isinstance(result, dict):
        for key in ("records", "results"):
            val = result.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
    return []


def _pick(data: dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        if k in data and data[k] not in (None, ""):
            return str(data[k])
    return None


def _flatten(record: dict[str, Any]) -> str:
    parts = []
    for k, v in record.items():
        if v in (None, ""):
            continue
        parts.append(f"{k}: {v}")
    return " | ".join(parts)[:4000]


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        return None
