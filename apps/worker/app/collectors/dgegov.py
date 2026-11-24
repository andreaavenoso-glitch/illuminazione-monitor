"""Reader for the albo / "bandi di gara e contratti" pages of the dgegovpa.it portal (ASP.NET, used by many comuni).

The generic gate cannot read these pages well: in the albo the title of an act is a text next to (not inside) the link
to its PDF, and in the bandi table the rows carry no link at all, only a "Dettaglio" button. So the entries are read
here from the portal's own markup:

* albo: one block per act (``RptAlbo_ctlNN_divFirst`` ...): number, date, title, kind, sector, act number, PDFs;
* bandi: one table row per procedure (``tblbandi``): date, CIG, title.

Pure functions, no network. A page of this portal that holds no entry of interest is "skip": the filter lists of the
portal ("Finanza di progetto", "Concessioni e partenariato...") would otherwise send the whole page to Claude.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_ALBO_ITEM = re.compile(r"RptAlbo_ctl(\d+)_divFirst$")
_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
PAGE_PARAM = "_mpag"  # added by the browser script to tell the pages of a list apart
SEARCH_PARAM = "_q"  # ... and the searches (keyword) made on a search page


def clean_url(url: str) -> str:
    """The address of the page without the page marker and the fragment: what a person can open."""
    parts = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in (PAGE_PARAM, SEARCH_PARAM)])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def cig_url(base_url: str, cig: str) -> str:
    """Address of a procedure: the list page plus its CIG (the portal opens a detail by a button, it has no address)."""
    base = clean_url(base_url)
    return f"{base}{'&' if '?' in base else '?'}cig={cig}"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_portal_page(soup: BeautifulSoup) -> bool:
    return soup.find(id=_ALBO_ITEM) is not None or soup.find("table", id="tblbandi") is not None or bool(
        soup.find(id=re.compile(r"RptAlbo_RptAlbo|RepBandi_ctl"))
    )


def albo_entries(soup: BeautifulSoup, base_url: str) -> list[dict[str, Any]]:
    out = []
    for first in soup.find_all(id=_ALBO_ITEM):
        # the smallest block that holds both the number box and the title column ("row" is also the class of the box)
        row = next((p for p in first.find_parents("div") if p.find("div", class_=re.compile(r"col-lg-10"))), None)
        if row is None:
            continue
        col = row.find("div", class_=re.compile(r"col-lg-10"))
        title_el = col.find("span", class_="h5") if col else None
        title = _norm(title_el.get_text(" ", strip=True)) if title_el else ""
        if not title:
            continue
        text = _norm(row.get_text(" ", strip=True))
        date_el = row.find(id=re.compile(r"divThird$"))
        m = _DATE.search(date_el.get_text(" ", strip=True) if date_el else text)
        pdfs = [a["href"] for a in row.find_all("a", href=True) if re.search(r"\.pdf(\?|$)", a["href"], re.I)]
        out.append({"title": title, "text": text, "date": m.group(0) if m else None, "href": pdfs[0] if pdfs else None})
    return out


def bandi_entries(soup: BeautifulSoup, base_url: str) -> list[dict[str, Any]]:
    table = soup.find("table", id="tblbandi")
    out = []
    for tr in (table.find_all("tr") if table else []):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        cig = _norm(tds[1].get_text(" ", strip=True))
        title = _norm(tds[2].get_text(" ", strip=True))
        if not title:
            continue
        m = _DATE.search(tds[0].get_text(" ", strip=True))
        out.append({"title": title, "cig": cig, "date": m.group(0) if m else None,
                    "text": f"CIG {cig} – {title}" + (f" (pubblicato il {m.group(0)})" if m else "")})
    return out


def is_detail_page(url: str) -> bool:
    """A procedure's detail page of the browser import (``...?cig=XXXX``): it only serves the deadline of its list entry."""
    return any(k == "cig" for k, _ in parse_qsl(urlsplit(url).query))
