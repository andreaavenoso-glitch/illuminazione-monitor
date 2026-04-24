"""ASMECOMM e-procurement collector.

https://piattaforma.asmecomm.it — platform serving ASMEL local authorities in
southern Italy. The public tender listing is an HTML table; individual rows
use ``tr.gara`` or ``tr.tender-row`` depending on the sub-portal.

The selectors below are a conservative best-effort and can be refined once the
live crawl is validated. If a row cannot be matched, the fallback anchor-scan
in :class:`HTMLCollectorBase` still surfaces in-scope results.
"""
from __future__ import annotations

from typing import ClassVar

from app.collectors.html_base import HTMLCollectorBase


class ASMECOMMCollector(HTMLCollectorBase):
    name = "asmecomm"
    listing_paths: ClassVar[tuple[str, ...]] = (
        "/bandi-avvisi",
        "/gare-scadute",
    )
    row_selectors: ClassVar[tuple[str, ...]] = (
        "table.gare tr",
        "tr.gara",
        "article.bando",
        "div.tender-row",
    )
    title_selectors: ClassVar[tuple[str, ...]] = (
        "td.oggetto a",
        "a.tender-title",
        "h2 a",
        "a",
    )
    date_selectors: ClassVar[tuple[str, ...]] = (
        "td.data-pubblicazione",
        "td.data",
        "span.date",
    )
    importo_selectors: ClassVar[tuple[str, ...]] = (
        "td.importo",
        "td.valore",
    )
