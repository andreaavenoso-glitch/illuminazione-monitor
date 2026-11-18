"""Best-first crawl of one comune's site, shared by the real scan and the dry run.

Notices are often buried several clicks deep, so instead of a fixed number of
levels the crawl keeps a priority queue of links scored by how likely they
are to lead to acts (legal section names, lighting / PPP wording, topic words;
junk and files are dropped) and always opens the best one next, until a page
budget, a depth cap or a time budget runs out.

Pages that carry the gate keywords are leaves (they are handed to ``on_page``
for analysis); pages that do not are treated as menus and expanded. The page
function and the fetch function are injected, so the same traversal serves
the paid scan (on_page = gate + Claude) and the free dry run (on_page = just
record what was seen).
"""
from __future__ import annotations

import asyncio
import heapq
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.collectors.page_gate import GateResult, host_of, normalize_url, rank_links, same_site

SEED_SCORE = 100  # links already chosen by the caller (sitemap, section names)
LINKS_PER_PAGE = 6
SECTION_SCORE = 20  # see page_gate.score_link: a link named like a legal section


class _Fetched(Protocol):
    text: str
    url: str | None
    error: str | None


@dataclass
class Visit:
    url: str
    depth: int
    action: str  # gate action, or "unreadable"
    error: str | None = None


@dataclass
class CrawlResult:
    visits: list[Visit] = field(default_factory=list)
    stopped_by: str = "exhausted"  # exhausted | pages | time


async def crawl(
    *,
    start_url: str,
    start_html: str,
    seeds: list[str],
    fetch: Callable[[str], Awaitable[_Fetched]],
    on_page: Callable[[str, str, int], Awaitable[GateResult]],
    max_pages: int,
    max_depth: int,
    time_budget_s: float,
    delay_s: float = 0.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> CrawlResult:
    """Visit the start page (depth 0), then the best-ranked links, deeper and
    deeper. ``max_pages`` counts fetched pages after the start page."""
    result = CrawlResult()
    visited = {normalize_url(start_url)}
    heap: list[tuple[float, int, str, int]] = []
    seq = 0

    def push(url: str, score: float, depth: int) -> bool:
        nonlocal seq
        key = normalize_url(url)
        if key in visited:
            return False
        visited.add(key)
        heapq.heappush(heap, (-score, seq, url, depth))
        seq += 1
        return True

    for u in seeds:
        push(u, SEED_SCORE, 1)

    def expand(html: str, page_url: str, depth: int) -> None:
        if depth >= max_depth:
            return
        for link, score in rank_links(html, base_url=page_url, limit=LINKS_PER_PAGE):
            # Stay on the comune's own site, except for links named exactly like
            # a section ("Albo pretorio", "Amministrazione trasparente", score
            # 20+): those often live on the platform vendor's host. A vendor's
            # marketing page (maggioli.com, joomla.it) is not one of them.
            if same_site(link, start_url) or same_site(link, page_url) or score >= SECTION_SCORE:
                push(link, score, depth + 1)

    gated = await on_page(start_url, start_html, 0)
    result.visits.append(Visit(start_url, 0, gated.action))
    if gated.action == "skip":
        expand(start_html, start_url, 0)

    started = clock()
    fetched = 0
    last_hit: dict[str, float] = {}  # host -> when we last asked it for a page
    while heap:
        if fetched >= max_pages:
            result.stopped_by = "pages"
            break
        if clock() - started >= time_budget_s:
            result.stopped_by = "time"
            break
        _, _, url, depth = heapq.heappop(heap)
        # Be polite: sites such as small comuni drop connections when pages are
        # requested back to back (seen as intermittent ConnectError / reset).
        host = host_of(url)
        wait = delay_s - (clock() - last_hit.get(host, -1e9))
        if wait > 0:
            await sleep(wait)
        last_hit[host] = clock()
        res = await fetch(url)
        fetched += 1
        if not res.text:
            result.visits.append(Visit(url, depth, "unreadable", res.error))
            continue
        page_url = res.url or url
        gated = await on_page(page_url, res.text, depth)
        result.visits.append(Visit(page_url, depth, gated.action))
        if gated.action == "skip":
            expand(res.text, page_url, depth)
    return result
