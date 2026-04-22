"""Generic HTML e-procurement portal collector base.

Italian e-procurement portals (ASMECOMM, Traspare, Tuttogare, SATER, START
Toscana, DigitalPA, Portale Appalti, Sintel, Net4market, …) ship tender listings
as plain HTML with predictable structural patterns: a table or list of rows,
each row containing a title link, a publication date and an "importo" column.

Rather than reimplement the scraping loop in every subclass we concentrate the
common behaviour here. A concrete collector declares:

    * ``listing_paths``    — URL paths relative to ``base_url`` to crawl
    * ``row_selectors``    — CSS selectors that select a tender row inside the
                             listing page (first that yields rows wins)
    * ``title_selectors``  — selectors for the title within a row (with href
                             resolution)
    * ``date_selectors``   — optional; extracted via ``parse_italian_date``
    * ``importo_selectors`` — optional; parsed via ``parse_importo``

The base takes care of HTTP fetch, HTML parsing, link resolution, perimeter
filtering (via ``is_in_lighting_perimeter``) and deduplication by absolute URL.
Subclasses that do not override the selectors fall back to heuristics that
scan every ``<a>`` tag whose surrounding text mentions a lighting keyword.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag
from parsing_rules import (
    days_until,
    is_in_lighting_perimeter,
    parse_importo,
    parse_italian_date,
)

from app.collectors.base import BaseCollector, CollectorError, RawRecordDraft


@dataclass
class ParsedRow:
    title: str | None
    link: str | None
    date: datetime | None = None
    importo: float | None = None
    snippet: str | None = None
    extras: dict = field(default_factory=dict)


class HTMLCollectorBase(BaseCollector):
    """Shared logic for HTML-scraping collectors. Subclass and override knobs."""

    listing_paths: ClassVar[tuple[str, ...]] = ("/",)
    row_selectors: ClassVar[tuple[str, ...]] = (
        "table.listing tr",
        "tr.tender-row",
        "article.bando",
        "li.bando",
        "div.bando",
        "div.tender-row",
    )
    title_selectors: ClassVar[tuple[str, ...]] = (
        "a.tender-title",
        "td.oggetto a",
        "h2 a",
        "h3 a",
        "a",
    )
    date_selectors: ClassVar[tuple[str, ...]] = (
        "td.data",
        "td.data-pubblicazione",
        "span.date",
        "time",
    )
    importo_selectors: ClassVar[tuple[str, ...]] = (
        "td.importo",
        "span.importo",
        "td.valore",
    )
    default_headers: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; LightingProcurementMonitor/0.1; "
            "+https://github.com/andreaavenoso-glitch/illuminazione-monitor)"
        ),
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
    }
    max_pages_per_path: ClassVar[int] = 1
    max_rows: ClassVar[int] = 100

    async def fetch(self, *, since: datetime | None = None) -> list[RawRecordDraft]:
        drafts: list[RawRecordDraft] = []
        seen_links: set[str] = set()

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self.default_headers,
        ) as client:
            for path in self.listing_paths:
                url = self._join(path)
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise CollectorError(f"{type(self).__name__} GET {url}: {exc}") from exc

                soup = BeautifulSoup(response.text, "lxml")
                rows = self._select_rows(soup)
                for row in rows[: self.max_rows]:
                    parsed = self.parse_row(row, base_url=url)
                    if parsed is None or not parsed.link:
                        continue
                    if parsed.link in seen_links:
                        continue
                    seen_links.add(parsed.link)

                    combined_text = " ".join(
                        filter(None, [parsed.title, parsed.snippet])
                    )
                    if not is_in_lighting_perimeter(combined_text):
                        continue

                    drafts.append(
                        RawRecordDraft(
                            raw_url=parsed.link,
                            raw_title=parsed.title,
                            raw_body=parsed.snippet,
                            raw_date=parsed.date,
                            extracted={
                                "platform": self.name,
                                "listing_url": url,
                                "importo_raw": parsed.importo,
                                "days_until": days_until(parsed.date),
                                **parsed.extras,
                            },
                        )
                    )
        return drafts

    def parse_row(self, row: Tag, *, base_url: str) -> ParsedRow | None:
        title, link = self._extract_title(row, base_url)
        if not title and not link:
            return None
        return ParsedRow(
            title=title,
            link=link,
            date=self._extract_date(row),
            importo=self._extract_importo(row),
            snippet=self._row_text(row),
        )

    def _select_rows(self, soup: BeautifulSoup) -> list[Tag]:
        for selector in self.row_selectors:
            rows = soup.select(selector)
            if rows:
                return rows
        # Fallback: any anchor surrounded by lighting keywords.
        anchors = [a for a in soup.find_all("a") if a.get("href")]
        return [a for a in anchors if is_in_lighting_perimeter(self._row_text(a))]

    def _extract_title(self, row: Tag, base_url: str) -> tuple[str | None, str | None]:
        for selector in self.title_selectors:
            node = row.select_one(selector)
            if node is None:
                continue
            href = node.get("href") if node.name == "a" else None
            if not href:
                link_node = node.find("a")
                if link_node and link_node.get("href"):
                    href = link_node.get("href")
            title = self._clean(node.get_text())
            link = urljoin(base_url, href) if href else None
            if title or link:
                return title, link
        # Fallback: treat row itself as anchor.
        if row.name == "a" and row.get("href"):
            return self._clean(row.get_text()), urljoin(base_url, row.get("href"))
        return None, None

    def _extract_date(self, row: Tag) -> datetime | None:
        for selector in self.date_selectors:
            node = row.select_one(selector)
            if node is None:
                continue
            candidate = node.get("datetime") or node.get_text()
            parsed = parse_italian_date(candidate)
            if parsed:
                return parsed
        return None

    def _extract_importo(self, row: Tag) -> float | None:
        for selector in self.importo_selectors:
            node = row.select_one(selector)
            if node is None:
                continue
            value = parse_importo(node.get_text())
            if value is not None:
                return float(value)
        return None

    def _row_text(self, node: Tag) -> str:
        return self._clean(node.get_text(" ", strip=True))

    @staticmethod
    def _clean(text: str | None) -> str | None:
        if text is None:
            return None
        cleaned = " ".join(text.split())
        return cleaned or None

    def _join(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return urljoin(self.base_url + "/", path.lstrip("/"))
