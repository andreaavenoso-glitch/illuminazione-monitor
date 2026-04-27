"""START Toscana collector.

https://start.toscana.it — e-procurement platform for Tuscany PA. Lists of
active tenders live at ``/tendering/tenders/advancedSearch.do`` with GET
parameters; the static page renders the first result page as HTML.
"""
from __future__ import annotations

from typing import ClassVar

from app.collectors.html_base import HTMLCollectorBase


class StartToscanaCollector(HTMLCollectorBase):
    name = "start_toscana"
    listing_paths: ClassVar[tuple[str, ...]] = (
        "/tendering/tenders/advancedSearch.do?searchType=2",
        "/tendering/tenders/openProcedures.do",
    )
    row_selectors: ClassVar[tuple[str, ...]] = (
        "table.listing tr",
        "tr.tender-row",
        "div.tender-card",
        "article.gara",
    )
    title_selectors: ClassVar[tuple[str, ...]] = (
        "td.title a",
        "a.tender-title",
        "h3 a",
        "a",
    )
    date_selectors: ClassVar[tuple[str, ...]] = (
        "td.pub-date",
        "td.data",
        "span.date",
    )
    importo_selectors: ClassVar[tuple[str, ...]] = (
        "td.amount",
        "td.importo",
    )
