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
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from shared_models.categories import GATE_KEYWORDS


def safe_join(base: str, href: str) -> str | None:
    """urljoin that returns None for hrefs Python cannot parse (for instance
    "http://[broken", which raises "Invalid IPv6 URL") instead of crashing a
    whole comune's scan on one bad link."""
    try:
        url = urljoin(base, href)
        urlsplit(url)
    except ValueError:
        return None
    return url


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
    # No block around the anchor: use its own text only, never the surrounding
    # body (neighbouring links would make an unrelated link look relevant).
    return a, _norm(a.get_text(" ", strip=True))[:_MAX_SNIPPET]


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
        absolute = safe_join(base_url, href)
        if absolute is None:
            continue
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


def gate_page(html: str, *, base_url: str, full_limit: int = 80_000) -> GateResult:
    """Decide what, if anything, goes to Claude for this page. The page is
    analysed whole here (it can be far longer than what Claude may receive:
    the entries of interest are often past the first 80 000 characters), and
    only the "full" fallback is cut to ``full_limit``."""
    template = detect_template(html)
    soup = BeautifulSoup(html, "lxml")
    text = _norm(soup.get_text(" ", strip=True)).lower()
    if not _has_gate_keyword(text):
        return GateResult("skip", "", template)
    cands = extract_candidates(soup, base_url)
    if cands:
        return GateResult("compact", _compact_html(cands), template, cands)
    return GateResult("full", html[:full_limit], template)


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
            url = safe_join(base_url, href)
            if url and url not in out and url != base_url:
                out.append(url)
        if len(out) >= limit:
            break
    return out


# --- Link ranking for the deep crawl -----------------------------------------
# Public bodies bury notices several clicks down (home -> Amministrazione
# Trasparente -> Bandi di gara e contratti -> Avvisi -> year -> list), so the
# crawl follows the most promising links first instead of a fixed depth.
_FILE_EXT = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".jpg", ".jpeg", ".png", ".gif",
    ".mp3", ".mp4", ".odt", ".ods", ".p7m", ".xml", ".json", ".csv", ".svg",
)
_JUNK = re.compile(
    # Site chrome and social links.
    r"contatt|privacy|cookie|login|accedi|area riservata|mappa del sito|rubrica|organigramma|"
    r"sindaco|giunta|consiglio comunale|eventi|turismo|cultura|sport|scuol|biblioteca|rss|"
    r"facebook|twitter|instagram|youtube|whatsapp|telegram|newsletter|accessibilit|credits|"
    r"note legali|\burp\b|"
    # Sections of Amministrazione Trasparente that never hold procurement acts.
    r"corruzion|personale|contrattazion|rendicont|sanzion|consulent|bilanc|concors|dotazione|"
    r"performance|patrimonio|beni immobili|pagament|organizzazione|enti controllati|incarichi|"
    r"tassi di assenza|dirigenti cessati|"
    # Everyday news that also says "avviso".
    r"elettor|elezion|servizio civile|matrimon|tessera",
    re.IGNORECASE,
)
# Topic words for a *menu entry*. Deliberately narrow: "trasparen", "contratt",
# "avvis(o)" or "determin" alone match unrelated sections (piano per la
# trasparenza, contrattazione, personale a tempo determinato, avviso agli elettori).
_TOPIC = re.compile(
    r"bandi di gara|bandi e|\bgare\b|\bgara\b|\bavvisi\b|contratti pubblici|affidament|"
    r"determinazion|\bdetermine\b|delibere|manifestazioni di interesse|\balbo\b|appalt|"
    r"finanza di progetto|partenariato|illuminazione|manutenzion|lavori pubblici|opere pubbliche|"
    r"atti delle amministrazioni",
    re.IGNORECASE,
)
_NEXT_TEXT = re.compile(r"^(pagina successiva|successiva|avanti|next|next page|»|›|>>)$", re.IGNORECASE)
# Menu entries are short ('Bandi di gara e contratti' = 25 characters); longer
# text is an act's own title, which the listing page already shows to the gate.
MAX_LINK_TEXT = 60
MIN_LINK_SCORE = 4


def _host(url: str) -> str:
    try:
        h = urlsplit(url).netloc.lower().split("@")[-1].split(":")[0]
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def same_site(a: str, b: str) -> bool:
    """Same host, or one a subdomain of the other (albo.comune.x.it)."""
    ha, hb = _host(a), _host(b)
    return bool(ha and hb) and (ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha))


def normalize_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.lower()
    path = parts.path.rstrip("/") or "/"
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme}://{_host(url)}{path}{query}".lower()


def score_link(text: str, href: str) -> int:
    """How promising a link is for finding pre-tender acts (0 = ignore)."""
    t = _norm(text).lower()
    if not t or len(t) > MAX_LINK_TEXT:
        return 0  # empty, or an act's own title rather than a menu entry
    h = href.lower()
    try:
        path = urlsplit(h).path
    except ValueError:
        return 0
    if _JUNK.search(t) or _JUNK.search(path):
        return 0
    if path.endswith(_FILE_EXT):
        return 0
    score = 0
    if any(label in t for label in SECTION_LABELS):
        score += 10
    if _has_gate_keyword(t):
        score += 6
    if _TOPIC.search(t):
        score += 4
    if _TOPIC.search(path):
        score += 2
    return score


def rank_links(html: str, *, base_url: str, limit: int = 12) -> list[tuple[str, int]]:
    """Promising links of a page, best first: (absolute url, score).
    Pagination links ("pagina successiva", rel=next) are kept with a fixed
    score so a listing can be followed past its first page."""
    soup = BeautifulSoup(html, "lxml")
    scores: dict[str, int] = {}
    urls: dict[str, str] = {}
    here = normalize_url(base_url)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue
        url = safe_join(base_url, href)
        if url is None:
            continue
        text = a.get_text(" ", strip=True)
        rel = [r.lower() for r in (a.get("rel") or [])]
        score = 7 if ("next" in rel or _NEXT_TEXT.match(_norm(text))) else score_link(text, url)
        key = normalize_url(url)
        if score >= MIN_LINK_SCORE and key != here and score > scores.get(key, 0):
            scores[key] = score
            urls[key] = url
    ranked = sorted(((urls[k], sc) for k, sc in scores.items()), key=lambda x: -x[1])
    return ranked[:limit]
