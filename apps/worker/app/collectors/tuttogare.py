"""Tuttogare e-procurement collector.

https://www.tuttogare.it — another multi-tenant Italian platform. Most tenant
sites expose "/PortaleAppalti/it/homepage.wp" as the entry point with a
listing at "/PortaleAppalti/it/ppgare_bandi_lista.wp".
"""
from __future__ import annotations

from typing import ClassVar

from app.collectors.html_base import HTMLCollectorBase


class TuttogareCollector(HTMLCollectorBase):
    name = "tuttogare"
    listing_paths: ClassVar[tuple[str, ...]] = (
        "/PortaleAppalti/it/ppgare_bandi_lista.wp",
        "/gare",
    )
    row_selectors: ClassVar[tuple[str, ...]] = (
        "table#tabellaGare tr",
        "tr.riga-gara",
        "div.gara-box",
        "article.gara",
    )
    title_selectors: ClassVar[tuple[str, ...]] = (
        "td.oggetto a",
        "a.oggetto-gara",
        "h3 a",
        "a",
    )
    date_selectors: ClassVar[tuple[str, ...]] = (
        "td.data-pubblicazione",
        "td.dataPubblicazione",
        "span.data",
    )
    importo_selectors: ClassVar[tuple[str, ...]] = (
        "td.importo",
        "td.importoBase",
    )
