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

# atto_tipo is what Claude labels each act it extracts from an albo page; it is
# the strongest signal because the model read the whole act, not a snippet.
ATTO_TIPO_CATEGORY = {
    "manifestazione_interesse": MANIFESTAZIONE,
    "indagine_mercato": MANIFESTAZIONE,
    "avviso_preinformazione": PRE_GARA,
    "determina_a_contrarre": PRE_GARA,
    "proposta_ppp": PRE_GARA,      # proposta di finanza di progetto / dichiarazione di pubblico interesse
    "incarico_ppp": PRE_GARA,      # advisor, valutatore, verifica PFTE for a PPP proposal
    "incarico_tecnico": PRE_GARA,  # PRIC, censimento impianti, diagnosi, progettazione
}

# Wording taken from real acts found on the web (comuni's own albi, ANAC
# opinions): "avviso di manifestazione di interesse con richiesta di
# preventivo" (Rosolini), "indagine di mercato ... operatori da invitare alla
# procedura negoziata" (Gambolo, Bertonico, Verona), "indagine ... requisiti
# ESCo" (Filadelfia).
MANIFESTAZIONE_KEYWORDS = [
    "manifestazione di interesse", "manifestazioni di interesse",
    "manifestazione d'interesse", "manifestazioni d'interesse",
    "indagine di mercato", "indagine esplorativa", "avviso esplorativo",
    "consultazione preliminare", "avviso di interesse",
    "operatori economici da invitare", "individuazione di operatori economici",
    "richiesta di preventivo", "requisiti di esco",
]
# PPP / finanza di progetto (art. 193 d.lgs. 36/2023): proposals from private
# parties, the public-interest declaration, the call that solicits proposals,
# and the assignments that support the evaluation (advisor, valutatore,
# verifica del PFTE; e.g. Ragusa's "manifestazione interesse verifica PFTE
# PPP illuminazione pubblica", Vigevano's technical-legal support).
PPP_KEYWORDS = [
    "finanza di progetto", "project financing", "partenariato pubblico privato",
    "partenariato pubblico-privato", "proposta di finanza", "proposta di project",
    "pubblico interesse", "sollecitazione di proposte", "sollecitare proposte",
    "iniziativa privata", "proponente", "pef asseverato", "piano economico finanziario",
    "art. 193", "articolo 193", "advisor", "valutatore", "valutazione della proposta",
    "valutazione delle proposte", "verifica del pfte", "verifica pfte",
    "verifica di fattibilita", "verifica di fattibilità", "supporto al rup",
    "supporto tecnico-amministrativo", "valutazione di convenienza",
]
PRE_GARA_KEYWORDS = PPP_KEYWORDS + [
    "preinformazione", "pre-informazione", "programmazione triennale",
    "programma triennale", "programma biennale", "ppp",
    "delibera di indirizzo", "atto di indirizzo",
    # Technical groundwork before a tender (PRIC = piano regolatore
    # dell'illuminazione comunale; the "PICCS" term used in an earlier version
    # of this list has no source and was removed).
    "piano regolatore dell'illuminazione", "piano regolatore illuminazione", "pric",
    "piano dell'illuminazione", "piano illuminotecnico",
    "censimento degli impianti", "censimento dell'impianto", "diagnosi energetica",
    "audit energetico", "studio di fattibilita", "studio di fattibilità",
    "progetto di fattibilita", "progetto di fattibilità", "pfte",
]
# What counts as "lighting" for the free pre-filter. Beyond the core phrase
# these are the maintenance / replacement / efficiency wordings found in real
# notices (qualenergia.it listings): "manutenzione impianti di illuminazione
# pubblica", "sostituzione corpi illuminanti", "moduli retrofit a led",
# "conduzione e manutenzione", "gestione servizio illuminazione pubblica".
LIGHTING_KEYWORDS = [
    "illuminazione pubblica", "pubblica illuminazione", "illuminazione comunale",
    "illuminazione stradale", "impianti di illuminazione", "impianto di illuminazione",
    "punti luce", "punto luce", "corpi illuminanti", "apparecchi illuminanti",
    "sostituzione corpi", "retrofit", "relamping", "servizio luce",
    "efficientamento energetico", "riqualificazione energetica", "telegestione",
    "inquinamento luminoso", "conduzione e manutenzione", "illuminazione led",
    "impianti semaforici", "led",
]


# What lets a page through to the (paid) Claude extraction: lighting wording or
# a PPP / finanza di progetto signal (those acts often do not say
# "illuminazione" in the title). Deliberately a subset: generic words like
# "advisor" or "pubblico interesse" would let almost every page through.
GATE_KEYWORDS = LIGHTING_KEYWORDS + [
    "finanza di progetto", "project financing", "partenariato pubblico privato",
    "partenariato pubblico-privato", "proposta di finanza", "ppp", "art. 193",
    "articolo 193", "sollecitazione di proposte", "pric",
]


def _has(text: str, words: list[str]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text) for w in words)


def mentions_lighting(text: str | None) -> bool:
    return bool(text) and _has(text.lower(), LIGHTING_KEYWORDS)


def categorize(
    *,
    stato_procedurale: str | None,
    text: str | None,
    flag_pre_gara: str | None = None,
    atto_tipo: str | None = None,
) -> str | None:
    """pre_gara | manifestazione_interesse | gara, or None for esiti.

    Order: esito excluded; Claude's ``atto_tipo`` label when present; then the
    wording of the text; PRE-GARA state/flag; otherwise a published tender.
    """
    stato = (stato_procedurale or "").upper()
    if stato.startswith("ESITO"):
        return None
    if atto_tipo and atto_tipo in ATTO_TIPO_CATEGORY:
        return ATTO_TIPO_CATEGORY[atto_tipo]
    low = (text or "").lower()
    if _has(low, MANIFESTAZIONE_KEYWORDS):
        return MANIFESTAZIONE
    if stato == "PRE-GARA" or flag_pre_gara == "Yes" or _has(low, PRE_GARA_KEYWORDS):
        return PRE_GARA
    return GARA
