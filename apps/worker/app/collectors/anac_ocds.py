"""ANAC OCDS bulk collector — real national procurement data, not a
generic dashboard page.

Until now the "anac" platform_type was routed through SmartLLMCollector,
which just loads a single client-rendered Superset dashboard URL
(``dati.anticorruzione.it/superset/dashboard/appalti/``) and asks Claude to
read whatever happens to be visible — no query, no filter, no way to search
by keyword or CPV. A dedicated ``ANACCollector`` existed in ``anac.py`` for
a real search API, but it was dead code from the start: it calls a CKAN
``datastore/search`` endpoint with a ``q=``/``fq=`` filter and no
``resource_id`` — CKAN's ``datastore_search`` action requires ``resource_id``
and ANAC does not expose that kind of live full-text search at all. ANAC's
real, documented, working access path (confirmed against
https://github.com/AgID/cruscotto-italia's own production ETL, which pulls
this same feed) is bulk monthly OCDS (Open Contracting Data Standard)
release-package downloads — one JSON file per year/month covering every
public contract in Italy above threshold, filtered client-side here the
same way TED's CPV-scoped results and the watchlist scan already are.

URL pattern: https://dati.anticorruzione.it/opendata/download/dataset/ocds/filesystem/bulk/{YYYY}/{MM}.json
Publication lag is roughly 2 months, so only the last few already-published
months are worth requesting; a 404 just means "not published yet" and is
skipped, not an error.

The portal sits behind an F5 WAF that can reject automated requests outright
(seen firsthand: a plain curl -- even with a browser User-Agent -- came back
"Error 403 - Forbidden ... F5 site: ams9-ams" from a Codespaces IP, while the
same URL loaded fine from a residential browser). cruscotto-italia's own ETL
handles this by sniffing the response body for an HTML error page instead of
trusting the JSON content-type; we do the same here rather than letting a
WAF block masquerade as "ANAC has nothing this month".
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from app.collectors.base import BaseCollector, CollectorResult, RawRecordDraft
from parsing_rules import is_in_lighting_perimeter
from shared_models import RawRecord
from sqlalchemy.ext.asyncio import AsyncSession

ANAC_BULK_URL = (
    "https://dati.anticorruzione.it/opendata/download/dataset/ocds/filesystem/bulk/{year}/{month:02d}.json"
)

# Public-lighting CPV codes (same set used by the TED collector).
LIGHTING_CPV_CODES = {"34928510", "34993000", "50232000", "45316110"}

# ANAC publishes ~2 months behind; check the 3 most likely to already be
# available rather than guessing every month back to year start.
_LAG_MONTHS = 2
_LOOKBACK_MONTHS = 3

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# A file that's actually the WAF's HTML error page is always tiny compared
# to a real month of national procurement data.
_SUSPICIOUSLY_SMALL_BYTES = 100_000


def _months_to_check(now: datetime) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = now.year, now.month
    # Step back _LAG_MONTHS first (those are unlikely to be published yet),
    # then collect _LOOKBACK_MONTHS candidates from there.
    for _ in range(_LAG_MONTHS):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    for _ in range(_LOOKBACK_MONTHS):
        months.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return months


def _release_text(release: dict[str, Any]) -> str:
    tender = release.get("tender") or {}
    buyer = release.get("buyer") or {}
    parts = [
        tender.get("title") or "",
        tender.get("description") or "",
        buyer.get("name") or "",
    ]
    return " ".join(p for p in parts if p)


def _release_cpv_codes(release: dict[str, Any]) -> set[str]:
    tender = release.get("tender") or {}
    codes: set[str] = set()
    classification = tender.get("classification") or {}
    if classification.get("id"):
        codes.add(str(classification["id"]))
    for item in tender.get("items") or []:
        item_classification = (item or {}).get("classification") or {}
        if item_classification.get("id"):
            codes.add(str(item_classification["id"]))
    return codes


def _is_award_release(release: dict[str, Any]) -> bool:
    awards = release.get("awards") or []
    return any((a or {}).get("status") == "active" for a in awards)


def _release_importo(release: dict[str, Any]) -> float | None:
    tender = release.get("tender") or {}
    tender_value = (tender.get("value") or {}).get("amount")
    if tender_value is not None:
        return tender_value
    for award in release.get("awards") or []:
        award_value = ((award or {}).get("value") or {}).get("amount")
        if award_value is not None:
            return award_value
    return None


def _release_cig(release: dict[str, Any]) -> str | None:
    # OCDS-IT convention: tender.id carries the CIG. Only trust it when it
    # actually looks like one (10 alphanumeric chars) rather than assume the
    # convention holds for every release in the feed.
    tender_id = (release.get("tender") or {}).get("id")
    if tender_id and len(str(tender_id)) == 10 and str(tender_id).isalnum():
        return str(tender_id)
    return None


class ANACOCDSCollector(BaseCollector):
    name: ClassVar[str] = "anac_ocds"

    async def fetch(self, *, since: datetime | None = None) -> list[RawRecordDraft]:  # noqa: ARG002
        now = datetime.now(tz=UTC)
        drafts: list[RawRecordDraft] = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        ) as http:
            for year, month in _months_to_check(now):
                releases = await self._fetch_month(http, year, month)
                for release in releases:
                    if not self._matches_perimeter(release):
                        continue
                    drafts.append(self._to_draft(release, year=year, month=month))
        return drafts

    async def _fetch_month(self, http: httpx.AsyncClient, year: int, month: int) -> list[dict[str, Any]]:
        url = ANAC_BULK_URL.format(year=year, month=month)
        try:
            resp = await http.get(url)
        except httpx.HTTPError:
            return []

        if resp.status_code == 404:
            # Not published yet (or no data that month) -- not an error.
            return []

        # The WAF can reject a request with a small HTML error page under
        # any status code (confirmed by hand: a plain 403 with an HTML body
        # for this exact endpoint) -- check the body before trusting the
        # status code either way, so a rejection never masquerades as
        # "ANAC has nothing this month".
        body = resp.content
        if len(body) < _SUSPICIOUSLY_SMALL_BYTES and b"<html" in body[:200].lower():
            return []

        if resp.status_code != 200:
            return []

        try:
            payload = resp.json()
        except ValueError:
            return []

        releases = payload.get("releases")
        return releases if isinstance(releases, list) else []

    def _matches_perimeter(self, release: dict[str, Any]) -> bool:
        if _release_cpv_codes(release) & LIGHTING_CPV_CODES:
            return True
        return is_in_lighting_perimeter(_release_text(release))

    def _to_draft(self, release: dict[str, Any], *, year: int, month: int) -> RawRecordDraft:
        tender = release.get("tender") or {}
        buyer = release.get("buyer") or {}
        ocid = release.get("ocid") or release.get("id") or f"{year}-{month:02d}"

        title = tender.get("title") or f"Bando ANAC — {buyer.get('name', 'ente sconosciuto')}"
        body_parts = [tender.get("description") or ""]
        is_award = _is_award_release(release)
        if is_award:
            body_parts.append("Tipo avviso: esito di aggiudicazione")

        raw_date: datetime | None = None
        date_str = release.get("date")
        if date_str:
            try:
                raw_date = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
                if raw_date.tzinfo is None:
                    raw_date = raw_date.replace(tzinfo=UTC)
            except ValueError:
                raw_date = None

        # OCDS releases have no public per-tender detail URL in the bulk
        # feed itself; anchor on the ocid the same way Consip/SmartLLM
        # synthesize a stable identity URL when the source gives none.
        url = f"https://dati.anticorruzione.it/opendata/ocds_it#ocid={ocid}"

        return RawRecordDraft(
            raw_url=url,
            raw_title=title,
            raw_body="; ".join(p for p in body_parts if p),
            raw_html=None,
            raw_date=raw_date,
            extracted={
                "ente": buyer.get("name"),
                "cig": _release_cig(release),
                "importo": _release_importo(release),
                "scadenza": (tender.get("tenderPeriod") or {}).get("endDate"),
                "procedura": tender.get("procurementMethodDetails") or tender.get("procurementMethod"),
                "extracted_by": "anac-ocds-bulk",
                "perimeter_prevalidated": True,
            },
        )

    async def persist(
        self,
        session: AsyncSession,
        drafts: list[RawRecordDraft],
    ) -> CollectorResult:
        # Perimeter filtering already happened in fetch() against CPV codes
        # and the full tender text -- the base keyword filter would just
        # re-check a subset of the same text.
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
