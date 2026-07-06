"""Unit tests for the TED (Tenders Electronic Daily) direct-API collector.

httpx is mocked via pytest-httpx -- no real network calls are made.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from app.collectors.ted_api import TED_SEARCH_URL, TEDCollector


def _notice(**overrides) -> dict:
    base = {
        "publication-number": "17484-2026",
        "notice-title": {"ita": "Manutenzione impianti di illuminazione pubblica"},
        "buyer-name": {"ita": ["Comune di Martano"]},
        "publication-date": "2026-01-12+01:00",
        "links": {"htmlDirect": {"ITA": "https://ted.europa.eu/it/notice/17484-2026/html"}},
    }
    base.update(overrides)
    return base


class TestTEDCollectorFetch:
    @pytest.mark.asyncio
    async def test_extracts_importo_from_total_value(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url=TED_SEARCH_URL,
            method="POST",
            json={"notices": [_notice(**{"total-value": 5493558.9})]},
        )
        collector = TEDCollector(uuid4(), "https://api.ted.europa.eu")
        drafts = await collector.fetch()
        assert len(drafts) == 1
        assert drafts[0].extracted["importo"] == 5493558.9

    @pytest.mark.asyncio
    async def test_falls_back_to_estimated_value_when_no_total_value(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url=TED_SEARCH_URL,
            method="POST",
            json={"notices": [_notice(**{"estimated-value-lot": ["5634419.40"]})]},
        )
        collector = TEDCollector(uuid4(), "https://api.ted.europa.eu")
        drafts = await collector.fetch()
        assert drafts[0].extracted["importo"] == ["5634419.40"]

    @pytest.mark.asyncio
    async def test_extracts_procedure_type(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url=TED_SEARCH_URL,
            method="POST",
            json={"notices": [_notice(**{"procedure-type": "open"})]},
        )
        collector = TEDCollector(uuid4(), "https://api.ted.europa.eu")
        drafts = await collector.fetch()
        assert drafts[0].extracted["procedura"] == "open"

    @pytest.mark.asyncio
    async def test_truncates_deadline_to_date_only(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url=TED_SEARCH_URL,
            method="POST",
            json={
                "notices": [
                    _notice(**{"deadline-receipt-tender-date-lot": ["2026-02-24+01:00"]})
                ]
            },
        )
        collector = TEDCollector(uuid4(), "https://api.ted.europa.eu")
        drafts = await collector.fetch()
        assert drafts[0].extracted["scadenza"] == "2026-02-24"

    @pytest.mark.asyncio
    async def test_award_notice_without_deadline_gets_none(self, httpx_mock) -> None:
        # Award notices (can-standard) legitimately carry no submission deadline.
        httpx_mock.add_response(
            url=TED_SEARCH_URL,
            method="POST",
            json={"notices": [_notice()]},
        )
        collector = TEDCollector(uuid4(), "https://api.ted.europa.eu")
        drafts = await collector.fetch()
        assert drafts[0].extracted["scadenza"] is None
        assert drafts[0].extracted["procedura"] is None
