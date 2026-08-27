"""Unit tests for the ANAC OCDS bulk collector.

httpx is mocked via pytest-httpx -- no real network calls are made (the real
dati.anticorruzione.it endpoint sits behind an F5 WAF that rejects automated
traffic outright, confirmed by hand from both a Codespaces IP and a plain
curl with a browser User-Agent).
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.collectors.anac_ocds import ANAC_BULK_URL, ANACOCDSCollector, _months_to_check


def _release(**overrides) -> dict:
    base = {
        "ocid": "ocds-abc123-2026-01",
        "id": "release-1",
        "date": "2026-01-12T10:00:00Z",
        "buyer": {"id": "01234567890", "name": "Comune di Martano"},
        "tender": {
            "title": "Manutenzione impianti di illuminazione pubblica",
            "description": "Servizio di manutenzione e relamping LED",
            "id": "A1B2C3D4E5",
            "value": {"amount": 250000},
            "tenderPeriod": {"endDate": "2026-02-20T12:00:00Z"},
            "procurementMethodDetails": "Procedura aperta",
        },
    }
    base.update(overrides)
    return base


def _payload(*releases: dict) -> dict:
    return {"releases": list(releases)}


def _month_url(year: int, month: int) -> str:
    return ANAC_BULK_URL.format(year=year, month=month)


class TestMonthsToCheck:
    def test_skips_the_lag_months_and_returns_lookback_window(self) -> None:
        months = _months_to_check(datetime(2026, 6, 15, tzinfo=UTC))
        # lag=2 -> starts at April 2026, then 3 months back from there.
        assert months == [(2026, 4), (2026, 3), (2026, 2)]

    def test_handles_year_rollover(self) -> None:
        months = _months_to_check(datetime(2026, 1, 15, tzinfo=UTC))
        assert months == [(2025, 11), (2025, 10), (2025, 9)]


class TestANACOCDSCollectorFetch:
    @pytest.mark.asyncio
    async def test_keeps_lighting_perimeter_releases_by_keyword(self, httpx_mock) -> None:
        collector = ANACOCDSCollector(uuid4(), "https://dati.anticorruzione.it")
        months = _months_to_check(datetime.now(tz=UTC))
        year, month = months[0]
        httpx_mock.add_response(
            url=_month_url(year, month),
            json=_payload(_release()),
        )
        for y, m in months[1:]:
            httpx_mock.add_response(url=_month_url(y, m), status_code=404)
        drafts = await collector.fetch()
        assert len(drafts) == 1
        assert "illuminazione" in drafts[0].raw_title.lower()

    @pytest.mark.asyncio
    async def test_drops_releases_outside_the_lighting_perimeter(self, httpx_mock) -> None:
        collector = ANACOCDSCollector(uuid4(), "https://dati.anticorruzione.it")
        months = _months_to_check(datetime.now(tz=UTC))
        year, month = months[0]
        httpx_mock.add_response(
            url=_month_url(year, month),
            json=_payload(
                _release(
                    tender={
                        "title": "Fornitura di materiale di cancelleria",
                        "description": "Carta, penne e toner per uffici comunali",
                        "id": "Z9Z9Z9Z9Z9",
                    }
                )
            ),
        )
        for y, m in months[1:]:
            httpx_mock.add_response(url=_month_url(y, m), status_code=404)
        drafts = await collector.fetch()
        assert drafts == []

    @pytest.mark.asyncio
    async def test_matches_by_cpv_code_even_without_lighting_keywords(self, httpx_mock) -> None:
        collector = ANACOCDSCollector(uuid4(), "https://dati.anticorruzione.it")
        months = _months_to_check(datetime.now(tz=UTC))
        year, month = months[0]
        httpx_mock.add_response(
            url=_month_url(year, month),
            json=_payload(
                _release(
                    tender={
                        "title": "Affidamento servizio pluriennale",
                        "description": "Dettagli nel capitolato",
                        "classification": {"id": "34928510"},
                    }
                )
            ),
        )
        for y, m in months[1:]:
            httpx_mock.add_response(url=_month_url(y, m), status_code=404)
        drafts = await collector.fetch()
        assert len(drafts) == 1

    @pytest.mark.asyncio
    async def test_award_release_is_flagged_esito_for_the_classifier(self, httpx_mock) -> None:
        collector = ANACOCDSCollector(uuid4(), "https://dati.anticorruzione.it")
        months = _months_to_check(datetime.now(tz=UTC))
        year, month = months[0]
        httpx_mock.add_response(
            url=_month_url(year, month),
            json=_payload(_release(awards=[{"id": "a1", "status": "active", "value": {"amount": 250000}}])),
        )
        for y, m in months[1:]:
            httpx_mock.add_response(url=_month_url(y, m), status_code=404)
        drafts = await collector.fetch()
        assert "aggiudicazione" in drafts[0].raw_body.lower()

    @pytest.mark.asyncio
    async def test_pending_award_is_not_flagged_esito(self, httpx_mock) -> None:
        collector = ANACOCDSCollector(uuid4(), "https://dati.anticorruzione.it")
        months = _months_to_check(datetime.now(tz=UTC))
        year, month = months[0]
        httpx_mock.add_response(
            url=_month_url(year, month),
            json=_payload(_release(awards=[{"id": "a1", "status": "pending"}])),
        )
        for y, m in months[1:]:
            httpx_mock.add_response(url=_month_url(y, m), status_code=404)
        drafts = await collector.fetch()
        assert "aggiudicazione" not in drafts[0].raw_body.lower()

    @pytest.mark.asyncio
    async def test_waf_html_error_page_is_treated_as_unavailable_not_a_crash(self, httpx_mock) -> None:
        collector = ANACOCDSCollector(uuid4(), "https://dati.anticorruzione.it")
        months = _months_to_check(datetime.now(tz=UTC))
        for y, m in months:
            httpx_mock.add_response(
                url=_month_url(y, m),
                status_code=403,
                text="<html><head><title>Error Page</title></head><body>Forbidden</body></html>",
            )
        drafts = await collector.fetch()
        assert drafts == []

    @pytest.mark.asyncio
    async def test_cig_only_extracted_when_it_looks_like_a_real_cig(self, httpx_mock) -> None:
        collector = ANACOCDSCollector(uuid4(), "https://dati.anticorruzione.it")
        months = _months_to_check(datetime.now(tz=UTC))
        year, month = months[0]
        httpx_mock.add_response(
            url=_month_url(year, month),
            json=_payload(_release(tender={**_release()["tender"], "id": "not-a-cig"})),
        )
        for y, m in months[1:]:
            httpx_mock.add_response(url=_month_url(y, m), status_code=404)
        drafts = await collector.fetch()
        assert drafts[0].extracted["cig"] is None
