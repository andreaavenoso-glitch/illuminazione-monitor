"""Links that are a JavaScript call instead of an address.

Some comuni's sites (the "EG0 … .HBL" platform and others) write the attachments of a notice as
``javascript:SCHIOCCIOLA('en=e1015&MESSA=PUBBLICA&DSK=0000V601026BK&NOME=avviso.pdf&FORM=pdf','EG0/EGDOCVISJS.HBL')``:
the page's script opens ``<site>/EG0/EGDOCVISJS.HBL?<parameters>``. Read as plain HTML such a link has no address, so the
documents of the notice were never found. Two shapes are resolved:

1. ``javascript:fn('<parameters>','<program>.HBL')``  ->  ``<origin>/<program>.HBL?<parameters>``
2. ``javascript:fn('... /path/file.pdf ...')``         ->  the address of the file (pdf, zip, docx, xlsx) quoted in the call

The result is a guess at what the page's script does: it is only used to FETCH the document, and a response that is not a
readable document is simply ignored.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urljoin, urlsplit

_CALL_PROGRAM = re.compile(r"""javascript:\s*[\w.$]+\(\s*(['"])(?P<params>[^'"]*)\1\s*,\s*(['"])(?P<program>[^'"]+\.(?:hbl|php|asp|aspx|jsp|cgi|do))\3""", re.IGNORECASE)
_QUOTED_FILE = re.compile(r"""(['"])(?P<url>[^'"]+\.(?:pdf|zip|docx|xlsx)(?:\?[^'"]*)?)\1""", re.IGNORECASE)
FILE_FORMAT = re.compile(r"(?:^|[?&])FORM(?:AT)?=(pdf|zip|docx|xlsx)\b|(?:^|[?&])NOME=[^&]*\.(pdf|zip|docx|xlsx)\b", re.IGNORECASE)


def _encode_params(params: str) -> str:
    out = []
    for part in params.split("&"):
        key, sep, val = part.partition("=")
        out.append(f"{key}={quote(val, safe='')}" if sep else key)
    return "&".join(out)


def resolve_js_link(href: str, base_url: str) -> str | None:
    """The address a ``javascript:`` link opens, or None if it is not one of the known shapes."""
    h = (href or "").strip()
    if not h.lower().startswith("javascript:"):
        return None
    if m := _CALL_PROGRAM.search(h):
        p = urlsplit(base_url)
        return urljoin(f"{p.scheme}://{p.netloc}/", m.group("program").lstrip("/")) + "?" + _encode_params(m.group("params"))
    if m := _QUOTED_FILE.search(h):
        return urljoin(base_url, m.group("url"))
    return None


def file_name_from_url(url: str) -> str | None:
    """The file name carried in the query of such an address (``NOME=avviso.pdf``), for a readable document list."""
    from urllib.parse import parse_qs, unquote

    q = parse_qs(urlsplit(url).query)
    for key in ("NOME", "nome", "file", "filename"):
        if key in q and q[key]:
            return unquote(q[key][0])
    return None
