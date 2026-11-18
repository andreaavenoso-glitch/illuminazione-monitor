"""Deterministic pre-filter in front of the Claude extraction.

Reading a comune's page with Claude costs one call per page, and most pages
mention nothing about public lighting. This keeps the cheap, fixed part here:

1. If the page text carries none of the gate keywords (lighting wording, or a
   PPP / finanza di progetto signal), Claude is never called.
2. Otherwise the page's links are scanned for entries (anchor + the text
   around it) that match, and only those go to Claude as a compact list: a
   handful of lines instead of up to 80 000 characters of HTML.
3. If the keywords are on the page but not inside any link (plain text), the
   whole page still goes to Claude, so nothing is lost -- only cost saved.

Works for any site template. ``detect_template`` only labels the platform so
coverage per template can be measured before writing platform-specific
readers. Pure functions: no network, no LLM.
"""
from __future__ import annotations

import hashlib
import html as htmllib
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from shared_models.categories import GATE_KEYWORDS

MAX_CANDIDATES = 60
_MIN_ANCHOR_TEXT = 12
_MAX_SNIPPET = 500
_BLOCK_TAGS = ("li", "tr", "article", "p", "div", "section")
_DATE_RE = re.compile(r"\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")

# Section names of Amministrazione Trasparente (D.Lgs. 33/2013, Allegato 1)
# and of albo pages where pre-tender acts are filed. Used to follow links
# without asking Claude to choose them.
SECTION_LABELS = (
    "bandi di gara e contratti", "bandi di gara", "bandi e avvisi", "avvisi pubblici",
    "avvisi di preinformazione", "atti delle amministrazioni aggiudicatrici",
    "manifestazioni di interesse", "provvedimenti", "determinazioni", "determine",
    "delibere", "albo pretorio", "amministrazione trasparente",
)


@dataclass
class Candidate:
    title: str
    href: str
    snippet: str
    date: str | None = None


@dataclass
class GateResult:
    action: str  # "skip" | "compact" | "full"
    html: str
    template: str
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def digest(self) -> str:
        """Stable fingerprint of what would be sent to Claude. Page chrome
        (banners, dates in the footer) does not change it; a new relevant
        entry does."""
        return hashlib.sha1(self.html.encode("utf-8")).hexdigest()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has_gate_keyword(text_lower: str) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", text_lower) for k in GATE_KEYWORDS)


def detect_template(html: str) -> str:
    """Label the site platform from fingerprints in the HTML. Only used for
    statistics: which platforms deserve a dedicated reader."""
    low = html[:200_000].lower()
    if "halleyweb" in low or "halley.it" in low or "halley informatica" in low:
        return "halley"
    if "sicraweb" in low or "maggioli" in low:
        return "maggioli"
    if "urbi" in low and "padigitale" in low:
        return "urbi_padigitale"
    if "bootstrap-italia" in low or "it-header" in low or "design-comuni" in low or "comuni-italia" in low:
        return "design_italia"
    if "wp-content" in low:
        return "wordpress"
    return "other"


def _container(a):
    """Nearest block around an anchor, but not one that swallows the whole
    list (then the snippet would carry every neighbouring entry)."""
    node = a.parent
    while node is not None and node.name:
        if node.name in _BLOCK_TAGS:
            txt = _norm(node.get_text(" ", strip=True))
            if len(txt) <= 700:
                return node, txt
        node = node.parent
    txt = _norm(a.parent.get_text(" ", strip=True)) if a.parent else ""
    return a.parent or a, txt[:_MAX_SNIPPET]


def extract_candidates(soup: BeautifulSoup, base_url: str) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for a in soup.find_all("a", href=True):
        title = _norm(a.get_text(" ", strip=True))
        href = a["href"].strip()
        if len(title) < _MIN_ANCHOR_TEXT or not href:
            continue
        if href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue
        _, snippet = _container(a)
        blob = f"{title} {snippet}".lower()
        if not _has_gate_keyword(blob):
            continue
        absolute = urljoin(base_url, href)
        key = (absolute, title)
        if key in seen:
            continue
        seen.add(key)
        m = _DATE_RE.search(snippet)
        out.append(Candidate(title=title, href=absolute, snippet=snippet[:_MAX_SNIPPET], date=m.group(1) if m else None))
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def _compact_html(cands: list[Candidate]) -> str:
    rows = []
    for c in cands:
        extra = f" ({c.date})" if c.date else ""
        rows.append(
            f'<li><a href="{htmllib.escape(c.href, quote=True)}">{htmllib.escape(c.title)}</a>'
            f"{extra} {htmllib.escape(c.snippet)}</li>"
        )
    return "<ul>" + "".join(rows) + "</ul>"


def gate_page(html: str, *, base_url: str) -> GateResult:
    """Decide what, if anything, goes to Claude for this page."""
    template = detect_template(html)
    soup = BeautifulSoup(html, "lxml")
    text = _norm(soup.get_text(" ", strip=True)).lower()
    if not _has_gate_keyword(text):
        return GateResult("skip", "", template)
    cands = extract_candidates(soup, base_url)
    if cands:
        return GateResult("compact", _compact_html(cands), template, cands)
    return GateResult("full", html, template)


def pick_section_links(html: str, *, base_url: str, limit: int) -> list[str]:
    """Links whose visible text names a section where pre-tender acts are
    filed (by the legal section names). Deterministic replacement for asking
    Claude to choose among every link of a landing page."""
    soup = BeautifulSoup(html, "lxml")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        text = _norm(a.get_text(" ", strip=True)).lower()
        href = a["href"].strip()
        if not text or len(text) > 120 or not href:
            continue
        if href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue
        if any(label in text for label in SECTION_LABELS):
            url = urljoin(base_url, href)
            if url not in out and url != base_url:
                out.append(url)
        if len(out) >= limit:
            break
    return out
