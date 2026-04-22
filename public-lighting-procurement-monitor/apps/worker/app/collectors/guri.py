from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

from app.collectors.base import BaseCollector, CollectorError, RawRecordDraft
from parsing_rules import is_in_lighting_perimeter


class GURICollector(BaseCollector):
    """Gazzetta Ufficiale collector.

    Scans the RSS feeds of the 5ª Serie Speciale (Contratti pubblici). The
    base_url points to the GURI root; the feed path is appended here so the
    stored source base_url stays clean.
    """

    name = "guri"
    FEED_PATHS: tuple[str, ...] = (
        "/atto/serie_generale/caricaFeedRss",
        "/rss/5aSerieSpeciale",
        "/rss",
    )

    async def fetch(self, *, since: datetime | None = None) -> list[RawRecordDraft]:
        feed_url = self._feed_url()
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                response = await client.get(feed_url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise CollectorError(f"GURI feed request failed: {exc}") from exc

        feed_data = await asyncio.to_thread(feedparser.parse, response.content)

        drafts: list[RawRecordDraft] = []
        for entry in feed_data.entries or []:
            title = getattr(entry, "title", None)
            summary = getattr(entry, "summary", None) or getattr(entry, "description", None)
            link = getattr(entry, "link", None)
            if not link:
                continue
            combined = " ".join(filter(None, [title, summary]))
            if not is_in_lighting_perimeter(combined):
                continue

            drafts.append(
                RawRecordDraft(
                    raw_url=link,
                    raw_title=title,
                    raw_body=summary,
                    raw_date=_entry_date(entry),
                    extracted={
                        "feed_url": feed_url,
                        "entry_id": getattr(entry, "id", None),
                        "source": "guri",
                    },
                )
            )
        return drafts

    def _feed_url(self) -> str:
        if self.base_url.endswith(".xml") or self.base_url.endswith("/rss"):
            return self.base_url
        return f"{self.base_url}{self.FEED_PATHS[1]}"


def _entry_date(entry: Any) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
