"""Pages read by the user's own browser (portals that refuse the server's address) and sent to the app.

The file is a JSON ``{"origine": url, "pagine": [{"url": ..., "html": ...}]}``. Pure checks here, shared by the API (which
validates the upload) and the worker (which analyses the pages). Nothing is trusted: sizes are capped and only http(s)
pages with some text are kept.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

MAX_PAGINE = 80
MAX_HTML_PAGINA = 600_000
MAX_TOTALE = 12_000_000


class ImportError_(ValueError):
    """The uploaded file is not a valid page bundle (the message is shown to the user)."""


def valida_pagine(payload: Any) -> list[dict[str, str]]:
    """The clean list of {"url", "html"} (first occurrence of an address wins). Raises ImportError_ with a clear reason."""
    if not isinstance(payload, dict) or not isinstance(payload.get("pagine"), list):
        raise ImportError_("Il file non è un pacchetto di pagine: manca l'elenco «pagine». Va generato con lo script dell'app.")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    total = 0
    for p in payload["pagine"]:
        if not isinstance(p, dict):
            continue
        url, html = str(p.get("url") or "").split("#")[0], str(p.get("html") or "")
        try:
            ok = urlsplit(url).scheme in ("http", "https") and bool(urlsplit(url).netloc)
        except ValueError:
            ok = False
        if not ok or url in seen or len(html.strip()) < 200:
            continue
        html = html[:MAX_HTML_PAGINA]
        total += len(html)
        if total > MAX_TOTALE:
            break
        seen.add(url)
        out.append({"url": url, "html": html})
        if len(out) >= MAX_PAGINE:
            break
    if not out:
        raise ImportError_("Nessuna pagina utilizzabile nel file (indirizzi non validi o pagine vuote).")
    return out
