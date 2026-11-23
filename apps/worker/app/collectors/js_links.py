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
        # the program of this platform reads the extension after the LAST parameter up to a "&": without a closing "&"
        # it fails with "Indicizzazione errata"; the page's own script adds one (verified on a real site)
        params = _encode_params(m.group("params")).rstrip("&") + "&"
        return urljoin(f"{p.scheme}://{p.netloc}/", m.group("program").lstrip("/")) + "?" + params
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


# A tiny page whose only job is to send the browser to the real file: <script>location.href='/DOC/x.pdf'</script>
_REDIRECTS = (
    re.compile(r"""(?:window\.|document\.|top\.|self\.)?location(?:\.href)?\s*=\s*(['"])(?P<u>[^'"]+)\1""", re.IGNORECASE),
    re.compile(r"""location\.(?:replace|assign)\(\s*(['"])(?P<u>[^'"]+)\1""", re.IGNORECASE),
    re.compile(r"""window\.open\(\s*(['"])(?P<u>[^'"]+)\1""", re.IGNORECASE),
    re.compile(r"""<meta[^>]+http-equiv=["']?refresh["']?[^>]+content=["'][^"']*url=(?P<u>[^"'>\s]+)""", re.IGNORECASE),
)
SMALL_PAGE = 2500


def js_redirect_target(html: str, base_url: str) -> str | None:
    """Where a tiny redirect page sends the browser (None when the page is not one, or sends nowhere useful)."""
    if not html or len(html) > SMALL_PAGE:
        return None
    for rx in _REDIRECTS:
        if m := rx.search(html):
            target = m.group("u").strip()
            if target and not target.lower().startswith(("javascript:", "#", "about:")):
                return urljoin(base_url, target)
    return None


_DOWNLOAD_JSON = re.compile(r'''"K"\s*:\s*"DOWNLOAD".*?"PATH"\s*:\s*"(?P<path>[^"]+)"''', re.IGNORECASE | re.DOTALL)


def download_target_from_json(text: str, base_url: str) -> str | None:
    """Some platforms answer the call with ``{"K": "DOWNLOAD", "PATH": "http:///halley//ht/e1015/file.pdf"}``: the path
    of the real file, with the host left out (``http:///``) and doubled slashes. The file lives on the site itself."""
    if not text or len(text) > SMALL_PAGE:
        return None
    m = _DOWNLOAD_JSON.search(text)
    if not m:
        return None
    path = m.group("path").strip()
    real_host = re.match(r"^https?://([^/]+)/", path)
    if real_host:  # a complete address: leave it alone
        return path
    p = urlsplit(base_url)
    rest = re.sub(r"^https?:/*", "", path)
    rest = re.sub(r"/{2,}", "/", rest).lstrip("/")
    return f"{p.scheme}://{p.netloc}/{rest}" if rest else None


# --- the "EG0 .HBL" platform: the page's own script POSTs a small text body to the program and opens the PATH it answers ---
_BOUNDARY = "AZazAZ"
EG0_HEADERS = {"Content-Type": f"text/plain;charset=UTF-8; boundary={_BOUNDARY}"}


def is_eg0_call(url: str) -> bool:
    p = urlsplit(url)
    return p.path.lower().endswith(".hbl") and "MESSA=" in p.query


def eg0_post(url: str) -> tuple[str, bytes] | None:
    """(address, body) of the POST the platform's own script (``SCHIOCCIOLA``) sends for an address built by
    ``resolve_js_link``: the parameters go in the BODY, with real spaces, between the markers the program expects."""
    if not is_eg0_call(url):
        return None
    from urllib.parse import parse_qsl

    p = urlsplit(url)
    pairs = parse_qsl(p.query, keep_blank_values=True)  # decoded: "ver 3 NUOVO AVVISO.pdf", as the script sends it
    valmessa = "&".join(f"{k}={v}" for k, v in pairs)
    body = (
        f"--{_BOUNDARY}\r\n&name=\"protocollo={p.scheme}&ser={p.netloc}&{valmessa}&PAGINA=\"\r\n\n"
        f"\r\n--{_BOUNDARY}--\r\n"
    )
    return f"{p.scheme}://{p.netloc}{p.path}", body.encode("utf-8")
