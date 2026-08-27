"""Sitemap-first page discovery for municipal transparency sections.

Many comune CMS platforms (design_italia, Halley, Urbi...) auto-generate a
sitemap.xml listing every page on the site, including ones several clicks
deep that matching a single "Bandi di gara" link on the landing page would
never find. Checking it first is one HTTP call (two if it's a sitemap
index) and gives a far more complete picture of where pre-gara signals
might be filed than crawling links by hand.
"""
from __future__ import annotations

from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx
import structlog

log = structlog.get_logger(__name__)

_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml")

# Keep the candidate list bounded: a comune sitemap can list thousands of
# pages (news, services, events...); only ones whose URL plausibly relates
# to procurement/transparency are worth the extra fetch + extraction cost.
#
# Two tiers, not one flat list: a URL matching only a generic transparency
# term (avviso, delibera, determina...) is noisy -- on a comune's site that
# word shows up on TARI payment notices, election announcements, waste
# collection reminders, anything -- while MAX_EXTRA_PAGES downstream only
# ever reads the first 8 candidates returned here. Confirmed in production:
# 110 comuni scanned real, substantial pages and found zero lighting
# signals, because every one of the pages actually read (selected by an
# unranked keyword match) turned out to be about disability inclusion
# services, waste collection, or elections -- generic "avviso"/"delibera"
# hits crowding out whatever genuine "bandi-di-gara" page existed further
# down the sitemap. Procurement-specific terms are surfaced first so they
# survive that cap; generic ones only pad out remaining slots.
_STRONG_KEYWORDS = (
    "bandi",
    "gara",
    "appalt",
    "manifestazion",
    "indagin",
    "illuminazione",
    "relamping",
)
_WEAK_KEYWORDS = (
    "trasparen",
    "contratt",
    "albo",
    "avvis",
    "delibera",
    "determin",
)
_RELEVANT_KEYWORDS = _STRONG_KEYWORDS + _WEAK_KEYWORDS

MAX_SITEMAP_URLS = 15


async def discover_sitemap_urls(base_url: str, *, timeout: float = 20.0) -> list[str]:
    """Return up to MAX_SITEMAP_URLS URLs from the site's sitemap.xml that
    look relevant to procurement/transparency, or [] if no sitemap is found
    or none of its URLs look relevant. Follows one level of sitemap index
    (a <sitemapindex> pointing at further per-section sitemaps), capped at
    5 sub-sitemaps to bound the number of requests.
    """
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for path in _SITEMAP_PATHS:
            xml_text = await _fetch_xml(client, root + path)
            if xml_text is None:
                continue
            locs = _parse_locs(xml_text)
            if not locs:
                continue
            if _looks_like_sitemap_index(xml_text):
                sub_locs: list[str] = []
                for sub_url in locs[:5]:
                    sub_xml = await _fetch_xml(client, sub_url)
                    if sub_xml:
                        sub_locs.extend(_parse_locs(sub_xml))
                locs = sub_locs
            relevant = _filter_relevant(locs)
            if relevant:
                return relevant[:MAX_SITEMAP_URLS]
    return []


async def _fetch_xml(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None
        return resp.text
    except httpx.HTTPError as exc:
        log.info("sitemap.fetch_failed", url=url, error=str(exc))
        return None


def _looks_like_sitemap_index(xml_text: str) -> bool:
    return "<sitemapindex" in xml_text.lower()


def _parse_locs(xml_text: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    # Namespace-agnostic: sitemaps declare an xmlns, so strip any "{...}"
    # prefix ElementTree leaves on tag names instead of registering it.
    return [
        el.text.strip()
        for el in root.iter()
        if el.tag.rsplit("}", 1)[-1] == "loc" and el.text and el.text.strip()
    ]


def _filter_relevant(urls: list[str]) -> list[str]:
    """Relevant URLs, strong-keyword matches first (each tier keeps the
    sitemap's own order), so a downstream cap on how many get read favors
    procurement-specific pages over generic transparency ones.
    """
    strong: list[str] = []
    weak: list[str] = []
    for u in urls:
        lowered = u.lower()
        if any(k in lowered for k in _STRONG_KEYWORDS):
            strong.append(u)
        elif any(k in lowered for k in _WEAK_KEYWORDS):
            weak.append(u)
    return strong + weak
