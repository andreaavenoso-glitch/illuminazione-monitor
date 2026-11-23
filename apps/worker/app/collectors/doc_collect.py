"""The documents of one notice, read at two depths.

* ``base``        the notice page and the documents it links directly (a first look, a couple of minutes at most)
* ``approfondita``  the same, then the documents those documents link (a delibera that cites its attachments, the
                   technical report behind a determina): more levels, more documents, more time

Best-first (the most promising link first), always within a budget of documents, levels and seconds, so that a
deep reading is thorough but cannot run away. Pure with respect to the network: ``fetch`` is injected.
"""
from __future__ import annotations

import heapq
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.collectors.deadline_hunt import doc_links
from app.collectors.js_links import file_name_from_url

Fetch = Callable[[str], Awaitable[tuple[str, str | None]]]  # url -> (text, raw html or None)


@dataclass(frozen=True)
class Livello:
    max_docs: int
    depth: int
    budget_s: float
    per_page: int


LIVELLI: dict[str, Livello] = {
    "base": Livello(max_docs=9, depth=1, budget_s=120.0, per_page=8),
    "approfondita": Livello(max_docs=30, depth=3, budget_s=420.0, per_page=10),
}


@dataclass
class Collected:
    url: str
    name: str
    text: str
    depth: int


def doc_name(url: str) -> str:
    return file_name_from_url(url) or urlsplit(url).path.rsplit("/", 1)[-1] or urlsplit(url).netloc


async def collect_docs(
    start: str, fetch: Fetch, livello: Livello, *, clock: Callable[[], float] = time.monotonic,
) -> tuple[list[Collected], str]:
    """(documents in the order read, why it stopped). Unreadable documents are listed with empty text."""
    out: list[Collected] = []
    heap: list[tuple[int, int, str, int]] = [(0, 0, start, 0)]
    seen: set[str] = {start}
    n, t0, why = 0, clock(), "esauriti i documenti raggiungibili"
    while heap:
        if len(out) >= livello.max_docs:
            why = f"raggiunto il massimo di {livello.max_docs} documenti"
            break
        if clock() - t0 > livello.budget_s:
            why = f"tempo massimo ({int(livello.budget_s)} s) raggiunto"
            break
        _, _, url, depth = heapq.heappop(heap)
        text, raw = await fetch(url)
        out.append(Collected(url, "pagina dell'avviso" if depth == 0 else doc_name(url), text, depth))
        if raw and depth < livello.depth:
            for score, link in doc_links(raw, url, seen=seen, limit=livello.per_page):
                seen.add(link)
                n += 1
                heapq.heappush(heap, (-score, n, link, depth + 1))
    return out, why
