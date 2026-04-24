"""Unit tests for the HTML e-procurement collectors.

These tests exercise the parsing logic against local fixture files — no
network calls are made. httpx is mocked via pytest-httpx so the ``fetch``
pipeline runs end-to-end (including BeautifulSoup + perimeter filtering).
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from app.collectors.asmecomm import ASMECOMMCollector
from app.collectors.html_base import HTMLCollectorBase
from app.collectors.traspare import TraspareCollector
from app.collectors.tuttogare import TuttogareCollector
from bs4 import BeautifulSoup

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "html"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestAsmecommParsing:
    def test_row_selector_matches(self) -> None:
        collector = ASMECOMMCollector(uuid4(), "https://example.test")
        soup = BeautifulSoup(_load("asmecomm_listing.html"), "lxml")
        rows = collector._select_rows(soup)
        # 1 header row + 3 data rows all match "table.gare tr"; the header
        # has no anchors so parse_row will filter it out.
        assert len(rows) == 4

    def test_parse_extracts_title_link_date_importo(self) -> None:
        collector = ASMECOMMCollector(uuid4(), "https://example.test")
        soup = BeautifulSoup(_load("asmecomm_listing.html"), "lxml")
        rows = collector._select_rows(soup)
        parsed = [
            p
            for row in rows
            if (p := collector.parse_row(row, base_url="https://example.test/bandi-avvisi"))
            and p.link
        ]
        assert len(parsed) == 3
        titles = [p.title for p in parsed]
        assert any("Relamping LED" in t for t in titles if t)
        assert any("Accordo quadro illuminazione" in t for t in titles if t)

        row = next(p for p in parsed if p.title and "Relamping" in p.title)
        assert row.link.endswith("/bandi/12345")
        assert row.date is not None
        assert row.date.day == 15 and row.date.month == 4 and row.date.year == 2026
        assert row.importo == pytest.approx(1_250_000.0)


class TestTraspareParsing:
    def test_parses_card_grid(self) -> None:
        collector = TraspareCollector(uuid4(), "https://example.test")
        soup = BeautifulSoup(_load("traspare_listing.html"), "lxml")
        rows = collector._select_rows(soup)
        assert len(rows) == 2
        parsed = [
            collector.parse_row(r, base_url="https://example.test/procedure") for r in rows
        ]
        parsed = [p for p in parsed if p and p.link]
        assert len(parsed) == 2
        relamp = next(p for p in parsed if p.title and "Riqualificazione" in p.title)
        assert relamp.link.endswith("/procedure/987")
        assert relamp.importo == pytest.approx(890_000.0)


class TestTuttogareParsing:
    def test_table_rows(self) -> None:
        collector = TuttogareCollector(uuid4(), "https://example.test")
        soup = BeautifulSoup(_load("tuttogare_listing.html"), "lxml")
        rows = collector._select_rows(soup)
        assert len(rows) >= 2
        parsed = [
            collector.parse_row(r, base_url="https://example.test/")
            for r in rows
            if "riga-gara" in (r.get("class") or [])
        ]
        parsed = [p for p in parsed if p and p.link]
        assert len(parsed) == 2
        lighting = next(p for p in parsed if p.title and "illuminazione" in p.title.lower())
        assert lighting.importo == pytest.approx(3_400_000.0)


class TestPerimeterFilterInFetch:
    """End-to-end check: out-of-scope rows never reach RawRecordDraft."""

    @pytest.mark.asyncio
    async def test_fetch_returns_only_in_scope(self, httpx_mock) -> None:
        collector = ASMECOMMCollector(uuid4(), "https://asmecomm.test")
        for path in collector.listing_paths:
            httpx_mock.add_response(
                url=f"https://asmecomm.test{path}",
                text=_load("asmecomm_listing.html"),
            )
        drafts = await collector.fetch()
        titles = [d.raw_title for d in drafts]
        assert titles, "expected at least one in-scope draft"
        assert all(
            any(kw in (t or "").lower() for kw in ("illuminazione", "relamping"))
            for t in titles
        )
        assert not any("pulizia uffici" in (t or "").lower() for t in titles)


class TestGenericFallback:
    """HTMLCollectorBase anchor-scan fallback for pages without known selectors."""

    def test_anchor_fallback_picks_lighting_links(self) -> None:
        html = """
        <html><body>
          <p>Annunci vari</p>
          <a href="/bando/1">Riqualificazione illuminazione pubblica</a>
          <a href="/bando/2">Arredo urbano</a>
        </body></html>
        """
        collector = HTMLCollectorBase(uuid4(), "https://example.test")
        soup = BeautifulSoup(html, "lxml")
        # Force empty-match on the standard selectors to trigger fallback.
        rows = collector._select_rows(soup)
        # Fallback should return only the anchor with a lighting keyword.
        titles = [r.get_text(strip=True) for r in rows]
        assert any("illuminazione" in t.lower() for t in titles)
        assert not any("arredo urbano" in t.lower() for t in titles)
