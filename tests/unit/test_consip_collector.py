"""Unit tests for the Consip Open Data direct collector.

httpx is mocked via pytest-httpx -- no real network calls are made.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.collectors.consip_opendata import CONSIP_DATASET_URL, ConsipOpenDataCollector


def _item(**overrides) -> dict:
    base = {
        "#Denominazione_Bando": "AQ SERVIZIO LUCE 4",
        "Denominazione_Lotto": "Lotto 3 - Lombardia",
        "Categoria_Merceologica": "Energia",
        "Tipo_Strumento": "Accordo Quadro",
        "Tipo_Procedura": "Aperta",
        "Base_Asta": 1000000,
        "Data_Pubblicazione": "01-03-2026",
        "Identificativo_Lotto": "AQL123",
    }
    base.update(overrides)
    return base


def _mock_both_years(httpx_mock, *, current_year_items: list[dict] | None = None) -> None:
    now = datetime.now(tz=UTC)
    httpx_mock.add_response(
        url=CONSIP_DATASET_URL.format(year=now.year), json=current_year_items or []
    )
    httpx_mock.add_response(url=CONSIP_DATASET_URL.format(year=now.year - 1), json=[])


class TestConsipOpenDataCollector:
    @pytest.mark.asyncio
    async def test_maps_data_termine_to_scadenza_in_iso_format(self, httpx_mock) -> None:
        # data_termine ships as dd-mm-yyyy (hyphens); the shared
        # parse_italian_date used downstream only understands dd/mm/yyyy or
        # ISO, so scadenza must already be ISO by the time it leaves here.
        _mock_both_years(httpx_mock, current_year_items=[_item(Data_Termine="15-06-2026")])
        collector = ConsipOpenDataCollector(uuid4(), "https://dati.consip.it")
        drafts = await collector.fetch()
        assert len(drafts) == 1
        assert drafts[0].extracted["scadenza"] == "2026-06-15"

    @pytest.mark.asyncio
    async def test_missing_data_termine_leaves_scadenza_none(self, httpx_mock) -> None:
        _mock_both_years(httpx_mock, current_year_items=[_item(Data_Termine=None)])
        collector = ConsipOpenDataCollector(uuid4(), "https://dati.consip.it")
        drafts = await collector.fetch()
        assert drafts[0].extracted["scadenza"] is None

    @pytest.mark.asyncio
    async def test_unparseable_data_termine_leaves_scadenza_none_not_a_crash(self, httpx_mock) -> None:
        _mock_both_years(httpx_mock, current_year_items=[_item(Data_Termine="non una data")])
        collector = ConsipOpenDataCollector(uuid4(), "https://dati.consip.it")
        drafts = await collector.fetch()
        assert drafts[0].extracted["scadenza"] is None

    @pytest.mark.asyncio
    async def test_non_matching_lots_are_filtered_out(self, httpx_mock) -> None:
        _mock_both_years(
            httpx_mock,
            current_year_items=[
                _item(**{"#Denominazione_Bando": "AQ Materiale di cancelleria", "Denominazione_Lotto": ""})
            ],
        )
        collector = ConsipOpenDataCollector(uuid4(), "https://dati.consip.it")
        drafts = await collector.fetch()
        assert drafts == []
