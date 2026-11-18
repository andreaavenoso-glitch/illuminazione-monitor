"""The three information types Level 2 reports per region.

pre_gara                 signals before a tender exists (avvisi di
                         preinformazione, programmazione, project financing
                         proposals, PPP, delibere di indirizzo)
manifestazione_interesse expressions of interest / market surveys
gara                     published tenders and their amendments

Esiti (awards) are not one of the three: they are returned as ``None`` so
they stay out of the regional digest. The keyword lists are the proposal to
review; they are a free pre-filter and a cross-check, not the only signal.
"""
from __future__ import annotations

import re

PRE_GARA = "pre_gara"
MANIFESTAZIONE = "manifestazione_interesse"
GARA = "gara"
CATEGORIES = (PRE_GARA, MANIFESTAZIONE, GARA)

MANIFESTAZIONE_KEYWORDS = [
    "manifestazione di interesse", "manifestazioni di interesse",
    "indagine di mercato", "avviso esplorativo", "consultazione preliminare",
    "avviso di interesse", "richiesta di manifestazione",
]
PRE_GARA_KEYWORDS = [
    "preinformazione", "pre-informazione", "programmazione triennale",
    "programma triennale", "programma biennale", "proposta di project financing",
    "finanza di progetto", "partenariato pubblico privato", "ppp",
    "proposta di partenariato", "delibera di indirizzo", "atto di indirizzo",
    "piano illuminotecnico", "piccs", "pubblico interesse della proposta",
    "diagnosi energetica", "studio di fattibilita", "studio di fattibilità",
]
LIGHTING_KEYWORDS = [
    "illuminazione pubblica", "pubblica illuminazione", "impianti di illuminazione",
    "punti luce", "corpi illuminanti", "led", "efficientamento energetico",
    "servizio luce", "illuminazione stradale", "impianti semaforici",
]


def _has(text: str, words: list[str]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text) for w in words)


def mentions_lighting(text: str | None) -> bool:
    return bool(text) and _has(text.lower(), LIGHTING_KEYWORDS)


def categorize(*, stato_procedurale: str | None, text: str | None, flag_pre_gara: str | None = None) -> str | None:
    """pre_gara | manifestazione_interesse | gara, or None for esiti."""
    stato = (stato_procedurale or "").upper()
    if stato.startswith("ESITO"):
        return None
    low = (text or "").lower()
    if _has(low, MANIFESTAZIONE_KEYWORDS):
        return MANIFESTAZIONE
    if stato == "PRE-GARA" or flag_pre_gara == "Yes" or _has(low, PRE_GARA_KEYWORDS):
        return PRE_GARA
    return GARA
