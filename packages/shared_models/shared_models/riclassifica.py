"""What the documents of a notice say it really is, after the analysis.

A notice found in an albo or a news page is first classified from its title, which is often vague ("Avviso", "Allegati
tecnici", the title of the page). Once the documents have been read, the HEADING of an attached document tells what
it is: "Avviso pubblico per la presentazione di proposte di finanza di progetto" is a call for interest, a "Bando di
gara" is a tender, an "Avviso di aggiudicazione" is an outcome (noise).

Only the heading (the first lines) of each ATTACHED document is looked at: the whole text of a long avviso mentions
revocations, awards and proposals received in its premises and would classify as noise something that is open. The page
of the notice itself is not used: its first lines are the site's menu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from shared_models.categories import GARA, MANIFESTAZIONE, PRE_GARA, categorize
from shared_models.relevance import old_cig

HEAD = 900
RANK = {PRE_GARA: 0, MANIFESTAZIONE: 1, GARA: 2}
_CLOSED = re.compile(
    r"avviso di (?:aggiudicazione|esito)|esito di gara|aggiudicazione definitiva|post-?informazione|"
    r"revoca (?:in autotutela )?(?:della|del|dell.)\s*(?:procedura|avviso|bando|gara)|"
    r"annullamento (?:della )?(?:procedura|gara|avviso)",
    re.IGNORECASE,
)


# The title block ends where the premises begin: "1. Premesse", "Premesso che", "Considerato che", "Visto"...
_PREMISES = re.compile(r"\s(?:1\s?[.)]\s+[A-ZÀ-Ý]|premess[oae]\b|considerat[oae]\b|vist[oa]\b|art\.?\s*1\b)", re.IGNORECASE)


def title_block(text: str | None) -> str:
    """The first lines of a document up to its premises (at most ``HEAD`` characters)."""
    flat = " ".join((text or "").split())[:HEAD]
    m = _PREMISES.search(flat, 60)  # not the very beginning: a letterhead may start with "Visto"
    return flat[: m.start()] if m else flat


@dataclass(frozen=True)
class Verdetto:
    categoria: str | None  # manifestazione_interesse | gara: what a heading proves; None = nothing proven
    fonte: str | None  # the document that proves it
    chiuso: bool  # the heading says outcome / award / revocation: not an opportunity any more
    motivo: str


def verdetto_da_documenti(docs: list[tuple[str, str]]) -> Verdetto:
    """``docs`` = [(name, text)] of the ATTACHED documents, in the order read."""
    best: tuple[int, str, str] | None = None
    closed_by: str | None = None
    for name, text in docs:
        head = title_block(text)
        if len(head) < 40:
            continue
        cat = categorize(stato_procedurale=None, text=head)
        if cat in (MANIFESTAZIONE, GARA) and (best is None or RANK[cat] > best[0]):
            best = (RANK[cat], cat, name)
        if _CLOSED.search(head[:500]) and cat in (None, PRE_GARA) and closed_by is None:
            closed_by = name
    if best is not None:
        label = "una gara" if best[1] == GARA else "una manifestazione di interesse"
        return Verdetto(best[1], best[2], False, f"l'intestazione di «{best[2]}» è {label}")
    if closed_by is not None:
        return Verdetto(None, closed_by, True, f"l'intestazione di «{closed_by}» è un esito, un'aggiudicazione o una revoca")
    return Verdetto(None, None, False, "")


_EXECUTION = re.compile(
    r"liquidazion\w+\s+(?:di\s+spesa|(?:della\s+|delle\s+)?fattur\w+|(?:del\s+)?canon\w+)|\d+\s*[ªa°]?\s*mensilit|"
    r"canone\s+(?:del\s+)?mese|stato\s+avanzamento\s+lavori|\bs\.?a\.?l\.?\s+n",
    re.IGNORECASE,
)


def contratto_in_corso(page_text: str | None, cig: str | None) -> str | None:
    """Why a notice is the card of a contract already assigned and running (None if nothing says so): an old CIG, or
    acts of payment (liquidazione of mensilità, canoni, fatture) listed in its own page."""
    if old_cig(cig):
        return f"il CIG {cig} è anteriore al 2024: contratto già assegnato"
    if page_text and _EXECUTION.search(page_text):
        return "la pagina elenca atti di liquidazione (mensilità, canoni, fatture): contratto già in esecuzione"
    return None


def is_higher(new: str | None, current: str | None) -> bool:
    """A reclassification only moves a notice UP (pre-gara -> manifestazione -> gara), or out of 'not an opportunity'."""
    if new is None:
        return False
    return current is None or RANK[new] > RANK.get(current, 0)
