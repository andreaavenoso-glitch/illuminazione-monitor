"""The part of a web page that is the notice, without the site around it.

A comune's page carries a header menu ("Attuazione PNRR EU"), a sidebar with the latest news (with their dates), a
footer with the PEC and attachments of OTHER notices. Read as a whole, such a page gives a "finanziamento PNRR" that is
only the menu, a "data documento" that is the date of an unrelated news item, and documents (bus timetables) that
have nothing to do with the notice. ``main_region`` keeps the central part: <main> / <article> / the usual content
containers, after dropping navigation, header, footer, sidebars, widgets, breadcrumbs and cookie banners.

When the page has no recognisable structure, or the result is suspiciously short, the whole page is used: reading too
much is better than reading nothing.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

_DROP_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg"]
_DROP_SELECTORS = (
    '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]', '[role="complementary"]',
    '[class*="sidebar"]', '[id*="sidebar"]', '[class*="breadcrumb"]', '[class*="cookie"]', '[id*="cookie"]',
    '[class*="skip-"]', '[class*="back-to-top"]', '[class*="share"]',
)
_MAIN_SELECTOR = (
    "main, [role=main], article, #main, #content, #contenuto, .entry-content, .post-content, .page-content, "
    ".contenuto, .main-content, .content-area"
)
# The section with the attached documents often sits OUTSIDE the <article> that holds the description: it is kept.
_ATTACHMENTS = '[id*="allegat"], [class*="allegat"], [id*="attachment"], [class*="attachment"], [id*="download"], [class*="download"], [id*="documenti"]'
MIN_CHARS = 400


def _text(node) -> str:
    return " ".join(node.get_text(" ").split())


def main_region(html: str) -> str:
    """The central part of the page, as HTML (so its links can still be followed)."""
    soup = BeautifulSoup(html, "lxml")
    whole = len(_text(soup))
    for t in soup(_DROP_TAGS):
        t.decompose()
    for sel in _DROP_SELECTORS:
        for t in soup.select(sel):
            t.decompose()
    candidates = [c for c in soup.select(_MAIN_SELECTOR) if len(_text(c)) >= MIN_CHARS]
    node = max(candidates, key=lambda c: len(_text(c))) if candidates else (soup.body or soup)
    extra = []
    for sec in soup.select(_ATTACHMENTS):
        if sec is node or node in sec.parents or sec in node.parents:
            continue  # already inside the central part (or it IS the page)
        if any(sec in e.parents for e in extra) or any(e in sec.parents for e in extra):
            continue
        if sec.find("a", href=True):
            extra.append(sec)
    out = str(node) + "".join(str(e) for e in extra)
    # nothing left, or almost nothing compared to the page: the structure is not what we assumed
    return out if len(_text(node)) >= MIN_CHARS or whole < MIN_CHARS else html


def has_document_links(html: str) -> bool:
    """Does the HTML link at least one document (PDF, archive, Word, a file named like an avviso)?"""
    from app.collectors.deadline_hunt import doc_links

    return bool(doc_links(html, "https://example.invalid/", seen=set(), limit=1))


def main_text(html: str) -> str:
    return _text(BeautifulSoup(main_region(html), "lxml"))
