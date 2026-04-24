"""Traspare e-procurement collector.

https://traspare.it — multi-tenant platform used by many Italian municipalities.
Tender listings are rendered server-side as a <div class="card"> grid. Each
card contains a link to the dedicated tender page.
"""
from __future__ import annotations

from typing import ClassVar

from app.collectors.html_base import HTMLCollectorBase


class TraspareCollector(HTMLCollectorBase):
    name = "traspare"
    listing_paths: ClassVar[tuple[str, ...]] = (
        "/Home/Procedura",
        "/procedure/aperte",
    )
    row_selectors: ClassVar[tuple[str, ...]] = (
        "div.card.gara",
        "div.procedura",
        "article.procedura",
        "li.gara",
    )
    title_selectors: ClassVar[tuple[str, ...]] = (
        "h3 a",
        "h2 a",
        "a.titolo",
        "a",
    )
    date_selectors: ClassVar[tuple[str, ...]] = (
        "span.data-pubblicazione",
        "span.data",
        "time",
    )
    importo_selectors: ClassVar[tuple[str, ...]] = (
        "span.importo",
        "div.importo",
    )
