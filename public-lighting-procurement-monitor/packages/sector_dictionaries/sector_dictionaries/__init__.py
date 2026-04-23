"""Technical tag extraction, ported from scripts/pipeline.js:170-179."""
from __future__ import annotations

import re

_TAG_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("LED", re.compile(r"\b(led|relamp)\b", re.IGNORECASE)),
    ("telegestione", re.compile(r"telegest", re.IGNORECASE)),
    ("telecontrollo", re.compile(r"telecontr", re.IGNORECASE)),
    ("smart lighting", re.compile(r"smart[\s-]?light", re.IGNORECASE)),
    ("global service", re.compile(r"global[\s-]?serv", re.IGNORECASE)),
    ("accordo quadro", re.compile(r"accordo[\s-]?quad", re.IGNORECASE)),
    ("manutenzione", re.compile(r"manuten|gestione", re.IGNORECASE)),
    ("proroga", re.compile(r"proroga", re.IGNORECASE)),
    ("semafori accorpati", re.compile(r"semafor[ioci]|impianti\s+semaforic", re.IGNORECASE)),
)

_PNRR = re.compile(r"pnrr|pnc|react[\s.\-]?eu", re.IGNORECASE)
_PPP = re.compile(r"\bppp\b|concessione|project[\s.\-]?fin", re.IGNORECASE)


def extract_tags(text: str | None, importo: float | None = None) -> list[str]:
    if not text:
        text = ""
    tags: list[str] = []
    for label, pat in _TAG_RULES:
        if pat.search(text):
            tags.append(label)
    if _PNRR.search(text):
        tags.append("PNRR")
    if _PPP.search(text):
        tags.append("PPP")
    if importo is not None and importo > 5_538_000:
        tags.append("sopra soglia UE")
    return tags


__all__ = ["extract_tags"]
