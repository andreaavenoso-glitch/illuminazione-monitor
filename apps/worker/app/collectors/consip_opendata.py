"""Dedicated Consip Open Data collector.

Consip publishes a real open-data JSON feed of Convenzioni/Accordi
Quadro lots (framework-agreement tenders) — no HTML scraping or LLM
parsing needed. Confirmed by hand against the live CKAN catalog:

    GET https://dati.consip.it/api/3/action/package_show?id=dataset-bandi-e-gare
    -> resources include one JSON file per year:
       https://dati.consip.it/download/dataset/bandiegare{YEAR}.json

Each record is a single lot (not a single tender — an Accordo Quadro
like "AQ SERVIZIO LUCE" is split into ~10-15 regional lots). Fields
confirmed from a live sample: #Denominazione_Bando, Denominazione_Lotto,
Categoria_Merceologica, Data_Pubblicazione (DD-MM-YYYY), Tipo_Procedura,
Tipo_Strumento, Base_Asta, Identificativo_Lotto. No CIG, no per-lot URL
in the feed — records link back to the general Consip AQ landing page.

The dataset has no CPV/category filter fine-grained enough for lighting
(only "Strade, verde pubblico e gestione del territorio", which is far
broader) — filter by keyword match on the denomination fields instead,
confirmed against a live sample to catch both naming conventions Consip
uses ("AQ GESTIONE ED EFFICIENTAMENTO ENERGETICO DEGLI IMPIANTI DI
ILLUMINAZIONE PUBBLICA" and "AQ SERVIZIO LUCE" / "SERVIZIO LUCE 3/4" —
the latter doesn't contain the word "illuminazione" at all).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

import httpx
from app.collectors.base import BaseCollector, CollectorResult, RawRecordDraft
from shared_models import RawRecord
from sqlalchemy.ext.asyncio import AsyncSession

CONSIP_DATASET_URL = "https://dati.consip.it/download/dataset/bandiegare{year}.json"
CONSIP_LANDING_URL = "https://www.consip.it/bandi/aq-servizio-luce"

LIGHTING_KEYWORDS = ("illuminazione", "servizio luce", "efficientamento energetico degli impianti")


def _matches_lighting(bando: str, lotto: str) -> bool:
    text = f"{bando} {lotto}".lower()
    return any(kw in text for kw in LIGHTING_KEYWORDS)


def _parse_it_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d-%m-%Y").replace(tzinfo=UTC)
    except ValueError:
        return None


class ConsipOpenDataCollector(BaseCollector):
    name: ClassVar[str] = "consip_opendata"

    async def fetch(self, *, since: datetime | None = None) -> list[RawRecordDraft]:  # noqa: ARG002
        now = datetime.now(tz=UTC)
        years = {now.year, now.year - 1}

        items: list[dict] = []
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            for year in years:
                url = CONSIP_DATASET_URL.format(year=year)
                try:
                    resp = await http.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                except (httpx.HTTPError, ValueError):
                    continue
                if isinstance(data, list):
                    items.extend(data)

        drafts: list[RawRecordDraft] = []
        for item in items:
            bando = item.get("#Denominazione_Bando", "") or ""
            lotto = item.get("Denominazione_Lotto", "") or ""
            if not _matches_lighting(bando, lotto):
                continue

            title = f"{bando} — {lotto}" if lotto else bando
            body_parts = [
                f"Categoria: {item.get('Categoria_Merceologica', '')}",
                f"Tipo strumento: {item.get('Tipo_Strumento', '')}",
                f"Tipo procedura: {item.get('Tipo_Procedura', '')}",
            ]
            base_asta = item.get("Base_Asta")
            if base_asta:
                body_parts.append(f"Base asta: {base_asta}")

            lotto_id = item.get("Identificativo_Lotto", "")
            # normalize_records treats raw_url (-> link_bando) as the unique
            # identity of a tender. The Consip feed gives no per-lot detail
            # page, but every raw_url must still be distinct per lot or all
            # ~60 regional lots collapse into a single procurement_record on
            # upsert (confirmed in production: 77 raw_records -> 1 merged
            # record). Append the lot ID as a fragment to keep the landing
            # page as the real clickable link while giving each lot its own
            # identity.
            lot_url = f"{CONSIP_LANDING_URL}#lotto={lotto_id}" if lotto_id else CONSIP_LANDING_URL
            drafts.append(
                RawRecordDraft(
                    raw_url=lot_url,
                    raw_title=title,
                    raw_body="; ".join(p for p in body_parts if p),
                    raw_html=None,
                    raw_date=_parse_it_date(item.get("Data_Pubblicazione")),
                    extracted={
                        "identificativo_lotto": lotto_id,
                        "categoria_merceologica": item.get("Categoria_Merceologica"),
                        "tipo_strumento": item.get("Tipo_Strumento"),
                        "base_asta": base_asta,
                        "data_attivazione": item.get("Data_Attivazione"),
                        "data_termine": item.get("Data_Termine"),
                        "extracted_by": "consip-opendata-direct",
                    },
                )
            )
        return drafts

    async def persist(
        self,
        session: AsyncSession,
        drafts: list[RawRecordDraft],
    ) -> CollectorResult:
        # Skip the keyword-perimeter filter — already scoped to lighting AQ
        # lots via _matches_lighting() in fetch().
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
