"""SATER (Intercent-ER) collector.

https://piattaformaintercenter.regione.emilia-romagna.it — the central
e-procurement system for Emilia-Romagna. Public tenders are listed under
``/portale/Amministrazione/Bandi_gara``.

Note: SATER often renders listings via AJAX. Where the static HTML exposes
enough data we stay on httpx; when it does not, a Playwright-backed variant
will be added in Sprint 10 alongside the anomaly engine.
"""
from __future__ import annotations

from typing import ClassVar

from app.collectors.html_base import HTMLCollectorBase


class SATERCollector(HTMLCollectorBase):
    name = "sater"
    listing_paths: ClassVar[tuple[str, ...]] = (
        "/portale/Amministrazione/Bandi_gara",
        "/portale/bandi",
    )
    row_selectors: ClassVar[tuple[str, ...]] = (
        "div.bando-item",
        "article.bando",
        "tr.gara",
        "li.bando",
    )
    title_selectors: ClassVar[tuple[str, ...]] = (
        "h3.titolo-bando a",
        "a.titolo-bando",
        "h2 a",
        "a",
    )
    date_selectors: ClassVar[tuple[str, ...]] = (
        "span.data-pubblicazione",
        "time.pub-date",
        "span.data",
    )
    importo_selectors: ClassVar[tuple[str, ...]] = (
        "span.importo-gara",
        "div.importo",
    )
