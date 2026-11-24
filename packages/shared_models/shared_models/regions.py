"""Italian regions: canonical names, aliases, and routing helpers.

Level 2 of the monitor is organised per region, so every record and every
watchlist entity needs one canonical region name. Sources spell it many ways
("Friuli-VG", "Emilia Romagna", "Trentino-Alto Adige/Südtirol"...); this
module maps them all to the 20 names below. Pure (no DB, no network).
"""
from __future__ import annotations

import re

REGIONS: list[str] = [
    "Abruzzo", "Basilicata", "Calabria", "Campania", "Emilia-Romagna",
    "Friuli-Venezia Giulia", "Lazio", "Liguria", "Lombardia", "Marche",
    "Molise", "Piemonte", "Puglia", "Sardegna", "Sicilia", "Toscana",
    "Trentino-Alto Adige", "Umbria", "Valle d'Aosta", "Veneto",
]

_ALIASES: dict[str, str] = {
    "friuli-vg": "Friuli-Venezia Giulia",
    "friuli": "Friuli-Venezia Giulia",
    "friuli venezia giulia": "Friuli-Venezia Giulia",
    "emilia romagna": "Emilia-Romagna",
    "trentino": "Trentino-Alto Adige",
    "alto adige": "Trentino-Alto Adige",
    "trentino alto adige": "Trentino-Alto Adige",
    "trentino-alto adige/sudtirol": "Trentino-Alto Adige",
    "trentino-alto adige/südtirol": "Trentino-Alto Adige",
    "valle d aosta": "Valle d'Aosta",
    "valle d’aosta": "Valle d'Aosta",
    "valle d'aosta/vallée d'aoste": "Valle d'Aosta",
    "sicilia": "Sicilia",
    "regione siciliana": "Sicilia",
}

# TED "place of performance" NUTS-2 codes.
NUTS2_REGION: dict[str, str] = {
    "ITC1": "Piemonte", "ITC2": "Valle d'Aosta", "ITC3": "Liguria",
    "ITC4": "Lombardia", "ITH1": "Trentino-Alto Adige", "ITH2": "Trentino-Alto Adige",
    "ITH3": "Veneto", "ITH4": "Friuli-Venezia Giulia", "ITH5": "Emilia-Romagna",
    "ITI1": "Toscana", "ITI2": "Umbria", "ITI3": "Marche", "ITI4": "Lazio",
    "ITF1": "Abruzzo", "ITF2": "Molise", "ITF3": "Campania", "ITF4": "Puglia",
    "ITF5": "Basilicata", "ITF6": "Calabria", "ITG1": "Sicilia", "ITG2": "Sardegna",
}


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().replace("_", " "))


def normalize_region(text: str | None) -> str | None:
    """Canonical region name for a free-text spelling, or None."""
    if not text or not text.strip():
        return None
    k = _key(text)
    for name in REGIONS:
        if _key(name) == k:
            return name
    return _ALIASES.get(k)


def region_from_nuts(code: str | None) -> str | None:
    if not code:
        return None
    return NUTS2_REGION.get(code.strip().upper()[:4])


# "Regione Lombardia", "Comune di X (Puglia)": a region named in the entity
# text itself is a strong hint (used when no watchlist entity matches).
_REGION_IN_TEXT = re.compile(
    r"\b(" + "|".join(re.escape(r) for r in sorted(REGIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def infer_region(
    *,
    regione: str | None = None,
    ente: str | None = None,
    entity_regions: dict[str, str] | None = None,
    nuts: str | None = None,
    provincia_text: str | None = None,
) -> str | None:
    """Best-effort region for a record, strongest signal first: explicit
    region, TED NUTS code, a watchlist entity with the same name, a region
    named inside the entity text. Returns None rather than guessing."""
    for candidate in (regione,):
        r = normalize_region(candidate)
        if r:
            return r
    r = region_from_nuts(nuts)
    if r:
        return r
    if ente and entity_regions:
        r = entity_regions.get(_key(ente))
        if r:
            return r
    for text in (ente, provincia_text):
        if text:
            m = _REGION_IN_TEXT.search(text)
            if m:
                return normalize_region(m.group(1))
    return None


def entity_key(name: str) -> str:
    return _key(name)
