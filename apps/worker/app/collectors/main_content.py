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
    out = str(node)
    # nothing left, or almost nothing compared to the page: the structure is not what we assumed
    return out if len(_text(node)) >= MIN_CHARS or whole < MIN_CHARS else html


def main_text(html: str) -> str:
    return _text(BeautifulSoup(main_region(html), "lxml"))
