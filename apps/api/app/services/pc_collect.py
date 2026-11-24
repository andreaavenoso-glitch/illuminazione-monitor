"""Which comuni must be read from the user's PC, and the report of that reading (pure functions, tested).

The server reads most sites. Some portals (dgegovpa.it, halleyweb.com...) refuse the address of a data centre: those, and
every comune whose last readings failed in a way that looks like a block, are listed for the PC script.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

BLOCKING_HOSTS = ("dgegovpa.it", "halleyweb.com")
BLOCK_ERRORS = {"reset", "timeout", "connect", "http_403", "http_429"}
STATI = {"ok", "non_riconosciuto", "errore"}


def _host(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower().split(":")[0].removeprefix("www.")
    except ValueError:
        return ""


def motivo_pc(urls: list[str], last_error: str | None, failures: int) -> str | None:
    """Why this comune is to be read from the PC, or None when the server reads it fine."""
    if any(_host(u) == h or _host(u).endswith("." + h) for u in urls for h in BLOCKING_HOSTS):
        return "portale che rifiuta il server"
    if failures and (last_error or "") in BLOCK_ERRORS:
        return f"sito non raggiungibile dal server ({last_error})"
    return None


def pulisci_rapporto(r: dict[str, Any]) -> dict[str, Any]:
    """The report as stored: known keys only, bounded sizes (it comes from outside)."""
    stato = r.get("stato") if r.get("stato") in STATI else "errore"
    ric = [{"parola": str(x.get("parola", ""))[:60], "trovati": bool(x.get("trovati"))} for x in (r.get("ricerche") or []) if isinstance(x, dict)][:20]
    return {
        "stato": stato,
        "pagine": max(0, min(int(r.get("pagine") or 0), 10_000)),
        "sezioni": max(0, min(int(r.get("sezioni") or 0), 1_000)),
        "ricerche": ric,
        "errori": [str(e)[:200] for e in (r.get("errori") or [])][:10],
        "note": str(r.get("note") or "")[:300],
    }
