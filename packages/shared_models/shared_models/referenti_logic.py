"""Rules for trusting a referente, how reliable an ente's contact set is, and what to do.

Rules decided on the Lombardia work (see README "Referenti"):
* the ente's own site is the base; a name is "verificato" only if the role is written next
  to it (``referenti.verify_person``) AND the page is recent enough:
* politici (sindaco, assessore): the page must be later than the last election
  (a page from before the vote is to be verified); when the election date is unknown, a page
  updated in the last 12 months. The press of the last 6 months is checked by hand (link).
* tecnici (responsabile, RUP): the page updated in the last 12 months, or a decree / act of
  appointment next to the name. Technical staff change mid-mandate, not at the vote.
Pure functions: no DB, no network.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import quote_plus

from shared_models.relevance import dates_in_text

POLITICI = ("sindaco", "assessore")
TECNICI = ("responsabile_tecnico", "rup")
ATTESI = ("sindaco", "assessore", "responsabile_tecnico")  # what a complete set has
FALLBACK_PEC = "alla c.a. del Sindaco, dell'Assessore ai LL.PP. e del Responsabile dell'Area Tecnica"
FRESH_DAYS = 365

_PAGE_DATE_CUE = re.compile(
    r"aggiornat\w+\s*(?:al|il|del)?|ultimo aggiornamento|data (?:di )?(?:ultimo )?aggiornamento|"
    r"data (?:di )?pubblicazione|pubblicat\w+ il|ultima modifica",
    re.IGNORECASE,
)
_ELECTION_CUE = re.compile(r"elezion\w+|proclamat\w+|eletto sindaco|rieletto", re.IGNORECASE)
_DECREE = re.compile(
    r"decreto (?:sindacale|del sindaco)|determina(?:zione)? di nomina|provvedimento di nomina|"
    r"nominat[oa] (?:con|responsabile)|incarico (?:conferito|di responsabile|di posizione)",
    re.IGNORECASE,
)


def page_date(text: str | None, today: date | None = None) -> date | None:
    """Latest "aggiornato al / ultimo aggiornamento / pubblicato il" date of a page."""
    today = today or date.today()
    found: list[date] = []
    for m in _PAGE_DATE_CUE.finditer(text or ""):
        ds = [d for d in dates_in_text((text or "")[m.end(): m.end() + 40]) if d <= today]
        if ds:
            found.append(ds[0])
    return max(found) if found else None


def election_date(text: str | None, today: date | None = None) -> date | None:
    """Date of the last municipal election written in a page ("elezioni comunali del
    9 giugno 2024"), or None."""
    today = today or date.today()
    found: list[date] = []
    for m in _ELECTION_CUE.finditer(text or ""):
        ds = [d for d in dates_in_text((text or "")[m.end(): m.end() + 90]) if d <= today and d.year >= 2000]
        if ds:
            found.append(ds[0])
    return max(found) if found else None


def has_decree(window: str | None) -> bool:
    return bool(_DECREE.search(window or ""))


def freshness(
    ruolo: str,
    data_fonte: date | None,
    elezione: date | None,
    decree: bool,
    today: date | None = None,
) -> tuple[bool, str | None]:
    """(still trustworthy, reason when not)."""
    today = today or date.today()
    limit = today - timedelta(days=FRESH_DAYS)
    if ruolo in POLITICI:
        if data_fonte is None:
            return False, "pagina senza data di aggiornamento"
        if elezione is not None and data_fonte < elezione:
            return False, f"pagina del {data_fonte:%d/%m/%Y} precedente alle elezioni del {elezione:%d/%m/%Y}"
        if elezione is None and data_fonte < limit:
            return False, f"pagina del {data_fonte:%d/%m/%Y} (oltre 12 mesi) e data delle elezioni non trovata"
        return True, None
    if decree:
        return True, None
    if data_fonte is not None and data_fonte >= limit:
        return True, None
    return False, "pagina senza data o di oltre 12 mesi e nessun decreto di incarico"


def affidabilita(people: list[dict]) -> tuple[int, str]:
    """% of the expected roles (sindaco, assessore ai LL.PP., responsabile tecnico) that
    are verificato, and its label: certo 100, probabile 70-99, ipotetico below 70."""
    ok = {p["ruolo"] for p in people if p.get("stato") == "verificato"}
    pct = round(100 * len([r for r in ATTESI if r in ok]) / len(ATTESI))
    return pct, ("certo" if pct >= 100 else "probabile" if pct >= 70 else "ipotetico")


def azione(people: list[dict]) -> str:
    """What the contact data allows: Invia (assessore ai LL.PP. verified), Invia - verifica
    nomi (mayor verified, no delegate found: write to the mayor), Invia con cautela (nothing
    verified yet), Da cercare (nobody found)."""
    if not people:
        return "Da cercare"
    ok = {p["ruolo"] for p in people if p.get("stato") == "verificato"}
    if "assessore" in ok:
        return "Invia"
    if "sindaco" in ok:
        return "Invia – verifica nomi"
    return "Invia con cautela"


def press_search_url(ente: str) -> str:
    """Google News search of the last 6 months for the political changes of a comune."""
    q = quote_plus(f'"{ente}" giunta assessore lavori pubblici')
    return f"https://www.google.com/search?q={q}&tbm=nws&tbs=qdr:m6"
