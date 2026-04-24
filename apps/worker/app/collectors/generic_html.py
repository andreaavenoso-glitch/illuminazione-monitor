"""Fallback collector for HTML sources without a dedicated subclass.

Used for albo pretorio pages and long-tail portals where we have no known
selectors. Relies entirely on the heuristic anchor scan in
:class:`HTMLCollectorBase`.
"""
from __future__ import annotations

from app.collectors.html_base import HTMLCollectorBase


class GenericHTMLCollector(HTMLCollectorBase):
    name = "generic_html"
