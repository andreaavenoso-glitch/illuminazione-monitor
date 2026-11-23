"""Find the deadline of a notice by going deeper until it turns up (a published notice always has one).

Start from the notice's own link. If the page states the deadline, that is it. If not, follow the links that
lead to the notice's documents -- PDF attachments first, then "allegati", "scheda", "bando"... -- reading each
page / PDF in turn, up to a depth and a number of documents, and stop at the first document that gives a
deadline. Every step is recorded so the page can say what was tried (and why nothing was found: a scanned
PDF, a missing PDF reader, a blocked link).
"""
from __future__ import annotations

import heapq
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit

from app.collectors.page_gate import safe_join
from bs4 import BeautifulSoup
from shared_models.relevance import deadline_from_text

MAX_DOCS = 12
MAX_DEPTH = 3
BUDGET_S = 90.0
_SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".rar", ".7z", ".doc", ".docx", ".xls", ".xlsx", ".p7m", ".mp4")
_NAMED = re.compile(r"avviso|bando|disciplinare|invito|manifestazione|lettera|capitolato|proposte?|determina|delibera|allegat|"
                    r"document|scheda|dettaglio|scarica|download|pubblicazion", re.IGNORECASE)
_HREFISH = re.compile(r"\.pdf($|\?)|/download|/allegat|getfile|/documento|attachment|/scheda|/dettaglio|idallegato|fileid", re.IGNORECASE)


@dataclass
class Doc:
    url: str
    kind: str  # html | pdf
    text: str
    raw: str | None
    depth: int
    note: str = ""


@dataclass
class Hunt:
    deadline: date | None = None
    found_in: str | None = None
    docs: list[Doc] = field(default_factory=list)
    reason: str = ""

    @property
    def text(self) -> str:
        return " ".join(d.text for d in self.docs if d.text)

    def trail(self) -> str:
        """What was tried, in one line for the page."""
        parts = []
        for d in self.docs:
            tag = "PDF" if d.kind == "pdf" else "pagina"
            what = d.note or (f"{len(d.text)} caratteri" if d.text else "vuoto")
            parts.append(f"{tag} {urlsplit(d.url).path.rsplit('/', 1)[-1][:40] or urlsplit(d.url).netloc} ({what})")
        out = "; ".join(parts) if parts else "nessun documento apribile"
        if self.deadline:
            return f"scadenza letta in {urlsplit(self.found_in or '').path.rsplit('/', 1)[-1][:50]} dopo {len(self.docs)} documenti"
        return f"{out}. {self.reason}".strip()


Fetch = Callable[[str, int], Awaitable[Doc]]


def doc_links(raw: str, base_url: str, *, seen: set[str], limit: int = 8) -> list[tuple[int, str]]:
    """Promising links of a notice page, best first: PDFs, then documents named like the notice. A PDF may
    live on another host (a document store); a web page only on the notice's own site."""
    host = urlsplit(base_url).netloc
    best: dict[str, int] = {}
    for a in BeautifulSoup(raw, "lxml").find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        path = href.lower().split("?")[0]
        if path.endswith(_SKIP_EXT):
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        is_pdf = path.endswith(".pdf") or "pdf" in href.lower().split("?")[-1]
        named = bool(_NAMED.search(text)) and len(text) <= 120
        hrefish = bool(_HREFISH.search(href))
        score = (4 if is_pdf else 0) + (2 if named else 0) + (1 if hrefish else 0)
        if score < 2:
            continue
        url = safe_join(base_url, href)
        if not url or url in seen or url == base_url:
            continue
        if not is_pdf and urlsplit(url).netloc != host:
            continue
        url = url.split("#")[0]
        best[url] = max(best.get(url, 0), score)
    return sorted(((s, u) for u, s in best.items()), reverse=True)[:limit]


async def hunt_deadline(
    start: str, fetch: Fetch, *, max_docs: int = MAX_DOCS, max_depth: int = MAX_DEPTH, budget_s: float = BUDGET_S,
    clock: Callable[[], float] = time.monotonic,
) -> Hunt:
    h = Hunt()
    t0 = clock()
    heap: list[tuple[int, int, str, int]] = [(0, 0, start, 0)]
    seen: set[str] = {start}
    n = 0
    while heap and len(h.docs) < max_docs:
        if clock() - t0 > budget_s:
            h.reason = f"tempo massimo ({int(budget_s)} s) raggiunto"
            break
        _, _, url, depth = heapq.heappop(heap)
        doc = await fetch(url, depth)
        h.docs.append(doc)
        d = deadline_from_text(doc.text)
        if d is not None:
            h.deadline, h.found_in = d, url
            return h
        if doc.raw and depth < max_depth:
            for score, link in doc_links(doc.raw, url, seen=seen):
                seen.add(link)
                n += 1
                heapq.heappush(heap, (-score, n, link, depth + 1))
    if not h.reason:
        if heap:
            h.reason = f"limite di {max_docs} documenti raggiunto, restavano {len(heap)} link"
        else:
            h.reason = "nessun altro link a documenti da seguire"
    return h
