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
    "bando_gara": GARA,            # a tender already published, with offers still open
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


def _has(text: str, words: list[str]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text) for w in words)


def mentions_lighting(text: str | None) -> bool:
    return bool(text) and _has(text.lower(), LIGHTING_KEYWORDS)


# --- What is NOT an opportunity ------------------------------------------------
# Found by reading a real run (128 records from 78 Puglia comuni): about a third
# were acts of a contract already running or already awarded, or not notices at all.
_EXCLUDE = re.compile(
    # paying or managing a contract in progress
    r"liquidazion|pagamento (delle )?fattur|\bfattur[ae]\b|canone (del )?mese|canone mensile|extracanone|"
    r"saldo (incarico|competenze)|rendicontazion|"
    r"comunicazione contributo|contributi per investimenti|"
    # already awarded / closed / cancelled
    r"illuminazione votiva|lampade votive|luci votive|aggiudicazion|aggiudicat[oaie]\b|enel energia|post-?informazione|\besito\b|affidamento diretto|affidamento e impegno|presa d.atto|\brevoca\b|"
    r"approvazione verbale|\bverbale\b|"
    # running the contract, not winning it
    r"direttore (dell.|dell\u2019)?esecuzione|"
    # not a procurement notice
    r"segnalazione guasti|\bordinanza\b|avviso ai cittadini|protocollo d.intesa|protocollo d\u2019intesa|"
    r"assicurativ|polizza|batterie",
    re.IGNORECASE,
)
# "Impegno di spesa" alone is the payment of a contract in progress (noise); together with a process signal it
# is a pre-gara: the money set aside for the verifier of the proposal, for the advisor, for the maintenance.
_IMPEGNO_SPESA = re.compile(r"impegno di spesa|impegno (della )?spesa|impegna\w* la spesa|impegno contabile", re.IGNORECASE)
_IMPEGNO_CONTESTO = re.compile(
    r"verificator|verifica (del |della |dei )?(pfte|proposta|progetto)|advisor|consulen|supporto (tecnico|specialistico|al rup)|"
    r"manutenzion|finanza di progetto|project financing|\bpfte\b|\bppp\b|partenariato|proposta",
    re.IGNORECASE,
)
# A body that is not a stazione appaltante: its decisions are commentary, not tenders.
_EXCLUDED_ENTI = re.compile(r"anticorruzione|\banac\b", re.IGNORECASE)
# A page or menu title, not an act.
_GENERIC_TITLES = frozenset({
    "finanza di progetto", "avviso", "avvisi", "bandi di gara", "bandi di gara e contratti", "delibere",
    "determine", "determinazioni", "provvedimenti", "albo pretorio", "notizie", "comunicazioni",
})

# A published tender, as opposed to a call for interest or a preliminary act.
_GARA_STRONG = re.compile(
    r"bando di gara|procedura aperta|disciplinare di gara|avviso di gara|gara (europea|telematica|a procedura)",
    re.IGNORECASE,
)
_GARA_WEAK = re.compile(r"procedura negoziata|\brdo\b|lettera d.invito|lettera di invito", re.IGNORECASE)
# An open call for interest / proposals (art. 193 c.16 soliciting PPP proposals included).
_MANIFESTAZIONE_WORDING = re.compile(
    r"manifestazion\w* d.interesse|avviso (pubblico )?esplorativo|indagine (di mercato|esplorativa)|"
    r"sollecitazione di (manifestazion|proposte)|selezione di proposte|consultazione preliminare",
    re.IGNORECASE,
)


# "Manifestazione di interesse" to JOIN an energy community is addressed to citizens and
# businesses (customers / prosumers), not to suppliers: not a procurement opportunity,
# unless the comune is also looking for a partner/advisor/operator for it.
_CER = re.compile(r"comunit\w* energetic", re.IGNORECASE)
_CER_PROCUREMENT = re.compile(
    r"affidamento|gestione|realizzazione|progettazione|partner|advisor|operatore|gara|concessione|"
    r"finanza di progetto|impianto",
    re.IGNORECASE,
)

# An open call for PPP proposals (art. 193 d.lgs. 36/2023: "avviso pubblico per la
# presentazione di proposte alternative di finanza di progetto") is a call for interest
# even though Claude labels it "proposta_ppp". Not so the acts that DEAL WITH a proposal
# already received (valutazione, pubblico interesse, fattibilita').
_CALL_FOR_PROPOSALS = re.compile(
    r"avviso pubblic\w*[^.]{0,250}proposte|(presentazione|ricezione) di proposte|proposte alternative|"
    r"invito a presentare proposte",
    re.IGNORECASE,
)
_PROPOSAL_RECEIVED = re.compile(
    r"pervenut\w+|valutazione (della|delle|di)|pubblico interesse|fattibilit|dichiarazione di",
    re.IGNORECASE,
)
_ACT_START = re.compile(r"\s*(delibera|determin)", re.IGNORECASE)


def _is_open_call_for_proposals(low: str) -> bool:
    return bool(_CALL_FOR_PROPOSALS.search(low)) and not _PROPOSAL_RECEIVED.search(low)


def is_cer_membership(low: str) -> bool:
    return bool(_CER.search(low)) and not _CER_PROCUREMENT.search(low)


def is_noise(text: str | None, ente: str | None = None) -> bool:
    """True for acts that are not opportunities (payments, awards, generic pages,
    non-procuring bodies). Used on its own at ingestion; ``categorize`` applies it too."""
    if ente and _EXCLUDED_ENTI.search(ente):
        return True
    low = " ".join((text or "").lower().split())
    if low in _GENERIC_TITLES:
        return True
    if _IMPEGNO_SPESA.search(low) and not _IMPEGNO_CONTESTO.search(low):
        return True
    return bool(_EXCLUDE.search(low)) or is_cer_membership(low)


def categorize(
    *,
    stato_procedurale: str | None,
    text: str | None,
    flag_pre_gara: str | None = None,
    atto_tipo: str | None = None,
    ente: str | None = None,
    has_deadline: bool = False,
) -> str | None:
    """pre_gara | manifestazione_interesse | gara, or None (not an opportunity).

    Order: awards and esiti out; payments, running contracts and non-notices out;
    then the *wording* of the title (a published tender is a gara, an open call is
    a manifestazione) which beats Claude's ``atto_tipo`` label -- the label said
    "avviso_preinformazione" for "avviso esplorativo per manifestazione di
    interesse", and "proposta_ppp" for a "bando di gara"; then the label; then
    pre-tender signals; otherwise a published tender.
    """
    stato = (stato_procedurale or "").upper()
    if stato.startswith("ESITO") or is_noise(text, ente):
        return None
    low = (text or "").lower()
    if _GARA_STRONG.search(low):
        return GARA
    if _MANIFESTAZIONE_WORDING.search(low) or _has(low, MANIFESTAZIONE_KEYWORDS):
        return MANIFESTAZIONE
    if _is_open_call_for_proposals(low):
        return MANIFESTAZIONE
    # A PPP proposal page with a deadline is an open call (a delibera that accepts a
    # proposal has none).
    if atto_tipo == "proposta_ppp" and has_deadline and not _ACT_START.match(low) and not _PROPOSAL_RECEIVED.search(low):
        return MANIFESTAZIONE
    if _GARA_WEAK.search(low):
        return GARA
    if atto_tipo and atto_tipo in ATTO_TIPO_CATEGORY:
        return ATTO_TIPO_CATEGORY[atto_tipo]
    if stato == "PRE-GARA" or flag_pre_gara == "Yes" or _has(low, PRE_GARA_KEYWORDS):
        return PRE_GARA
    # An act that merely calls up one of the services is a pre-tender signal: it is a
    # GARA only when the source says a tender is published (structured portals).
    if stato.startswith(("GARA", "RETTIFICA")):
        return GARA
    return PRE_GARA


def categorize_record(r) -> str | None:
    """``categorize`` for a stored ProcurementRecord, plus the scope check: a notice
    that mentions none of the services (a lake-side infrastructure project, a bare
    "Determinazione Nr.95") is not an opportunity whatever its wording."""
    from shared_models.services import detect_services

    text = f"{r.descrizione or ''} {r.tipologia_gara_procedura or ''}"
    cat = categorize(
        stato_procedurale=r.stato_procedurale,
        text=text,
        flag_pre_gara=r.flag_pre_gara,
        atto_tipo=r.atto_tipo,
        ente=r.ente,
        has_deadline=getattr(r, "scadenza", None) is not None,
    )
    if cat is not None and not (r.servizio or detect_services(text)):
        return None
    return cat
