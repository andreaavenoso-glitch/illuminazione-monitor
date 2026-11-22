"""When a notice is still worth showing.

A deadline is binding: a notice whose deadline (``scadenza``) is before today is
over and is noise, whatever it is about. Without a deadline there is only the
publication date to go by, so very old notices (an "avviso" from two years ago
still sitting on an albo) are left out too. Pure functions.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import TypeVar

# A notice without a deadline is shown only if it was published in this window
# (or has no date at all: it cannot be judged, so it is kept).
MAX_AGE_DAYS = 180


def _as_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def today_utc() -> date:
    return datetime.now(tz=UTC).date()


def is_actionable(
    scadenza: date | datetime | None,
    data_pubblicazione: date | datetime | None,
    today: date | None = None,
    max_age_days: int = MAX_AGE_DAYS,
) -> bool:
    """False for a notice whose deadline has passed, or (no deadline) whose
    publication is older than ``max_age_days``."""
    today = today or today_utc()
    deadline = _as_date(scadenza)
    if deadline is not None:
        return deadline >= today
    published = _as_date(data_pubblicazione)
    if published is not None:
        return published >= today - timedelta(days=max_age_days)
    return True


def is_expired_record(record: dict, today: date | None = None) -> bool:
    """For an extracted record (dict with an ISO ``scadenza``): deadline in the past.
    An unreadable or missing deadline is not expired."""
    raw = record.get("scadenza")
    if not raw:
        return False
    try:
        deadline = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return False
    return deadline < (today or today_utc())


# --- The same act, listed several times ---------------------------------------
# A real run had the same determina on the albo, the transparency page and the
# news feed: 53 records carried an act number, only 45 were distinct acts.
_ACT = re.compile(
    r"(determin\w*|delibera\w*|deliberazione|decisione dirigenziale|decreto)\D{0,40}?"
    r"\b(?:n\.?|nr\.?|numero)\s*(\d{1,5})\s*(?:del|/)\s*[^,;\n]{0,25}?(20\d{2})",
    re.IGNORECASE,
)
_SLUG = re.compile(r"[^a-z0-9]+")
_DIGITS = re.compile(r"\d+")
T = TypeVar("T")


def _slug(text: str) -> str:
    return _SLUG.sub(" ", text.lower()).strip()


def act_signature(ente: str | None, text: str | None) -> str:
    """Same signature = same act. By ente + kind + number + year when the text
    carries them (determina N. 1277 del 18/11/2026), otherwise by the start of
    the title."""
    ente_key = _slug(ente or "")
    body = text or ""
    m = _ACT.search(body)
    if m:
        kind = "g" if m.group(1).lower().startswith(("delib", "decisione", "decreto")) else "d"
        return f"{ente_key}|{kind}{m.group(2)}/{m.group(3)}"
    title_key = _slug(_DIGITS.sub(" ", body))[:70]
    return f"{ente_key}|{title_key}"


def collapse_duplicates(items: list[T], signature: Callable[[T], str], rank: Callable[[T], tuple]) -> list[T]:
    """One item per signature: the one with the highest ``rank``. Keeps the order
    in which each act first appeared."""
    best: dict[str, T] = {}
    order: list[str] = []
    for it in items:
        k = signature(it)
        if k not in best:
            order.append(k)
            best[k] = it
        elif rank(it) > rank(best[k]):
            best[k] = it
    return [best[k] for k in order]


_IT_MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
              "settembre", "ottobre", "novembre", "dicembre"]


def mentions_date(text: str | None, d: date) -> bool:
    """Is this calendar day written anywhere in the text (20/11/2026, 20-11-2026,
    20.11.26, 2026-11-20, "20 novembre 2026")? Used to tell a real publication date
    from the current date that a model filled in by itself."""
    if not text:
        return False
    low = text.lower()
    day, month, year = d.day, d.month, d.year
    candidates = {
        f"{day:02d}/{month:02d}/{year}", f"{day}/{month}/{year}", f"{day:02d}-{month:02d}-{year}",
        f"{day}-{month}-{year}", f"{day:02d}.{month:02d}.{year}", f"{day}.{month}.{year}",
        f"{day:02d}/{month:02d}/{year % 100:02d}", f"{day:02d}.{month:02d}.{year % 100:02d}",
        d.isoformat(), f"{day} {_IT_MONTHS[month - 1]} {year}",
    }
    return any(c in low for c in candidates)


_NUM_DATE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b")
_TXT_DATE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_IT_MONTHS) + r")\s+(\d{4})\b", re.IGNORECASE)


def dates_in_text(text: str | None) -> list[date]:
    """Every calendar date written in the text (31/12/2025, 31-12-2025, 31.12.2025,
    "31 dicembre 2025"). Impossible dates are skipped."""
    if not text:
        return []
    found: list[date] = []
    for d, m, y in _NUM_DATE.findall(text):
        found.append((int(y), int(m), int(d)))
    for d, mon, y in _TXT_DATE.findall(text):
        found.append((int(y), _IT_MONTHS.index(mon.lower()) + 1, int(d)))
    out: list[date] = []
    for y, m, d in found:
        try:
            out.append(date(y, m, d))
        except ValueError:
            continue
    return out


def only_old_dates(text: str | None, today: date, *, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """True when the text carries dates and ALL of them are older than the window:
    a detail page whose attachments are dated 2023 is an old, closed procedure even
    if the list entry showed no date. No dates at all -> False (cannot be judged)."""
    ds = dates_in_text(text)
    return bool(ds) and max(ds) < today - timedelta(days=max_age_days)


# --- Gare and manifestazioni: no false positives ---------------------------------
# A published tender or a call for interest ALWAYS has a deadline. One without a
# readable deadline cannot be confirmed open (its "published today" date was often
# just the day it was first seen), so it is kept out of the lists and the emails
# instead of risking a closed 2018 notice being sold as an open call.
STRICT_CATEGORIES = ("gara", "manifestazione_interesse")
_URL_YEAR = re.compile(r"(?<!\d)(20[0-3]\d)(?!\d)")


def url_year(url: str | None) -> int | None:
    """Latest year written in a link (".../2018/..."), a strong sign of an old document."""
    years = [int(y) for y in _URL_YEAR.findall(url or "")]
    return max(years) if years else None


def is_confirmed_open(
    category: str | None,
    scadenza: date | datetime | None,
    data_pubblicazione: date | datetime | None,
    url: str | None = None,
    today: date | None = None,
) -> bool:
    today = today or today_utc()
    deadline = _as_date(scadenza)
    if deadline is not None:
        return deadline >= today
    if category in STRICT_CATEGORIES:
        return False
    uy = url_year(url)
    if uy is not None and uy < today.year - 1:
        return False
    return is_actionable(None, data_pubblicazione, today)


# --- Reading the deadline out of a document -----------------------------------------
_DEADLINE_CUE = re.compile(
    r"scadenz\w*|entro (?:e non oltre )?(?:il|le ore|il giorno|la data)|non oltre (?:il|le ore)|"
    r"termine (?:ultimo |perentorio )?(?:per|di) (?:la )?(?:presentazione|ricezione|invio|partecipazione)|"
    r"presentat\w+ (?:entro|non oltre)",
    re.IGNORECASE,
)


_NOT_THE_DEADLINE = re.compile(r"regional|sopralluogo|chiariment|quesit", re.IGNORECASE)
_THE_DEADLINE = re.compile(
    r"propost|offert|candidatur|manifestazion|partecipazion|presentazion|pervenire", re.IGNORECASE
)


def deadline_from_text(text: str | None) -> date | None:
    """Deadline written in a notice: the first date right after each cue ("scadenza",
    "entro il", "termine per la presentazione delle offerte...").

    A real avviso quotes several dates (the regional funding call, a site visit, the
    questions window): those near "regionale", "sopralluogo", "chiarimenti" are set aside,
    and cues about proposals / offers / applications win over the generic ones. Within the
    winning group the latest is taken. None when no cue is followed by a date.
    Deterministic and free: it settles most notices before any Claude call."""
    if not text:
        return None
    strong: list[date] = []
    generic: list[date] = []
    for m in _DEADLINE_CUE.finditer(text):
        window = text[m.end(): m.end() + 140]
        ps = _positions(window)
        if not ps:
            continue
        # the first date written after the cue, not the latest of the window
        tok, found = min(ps, key=lambda p: window.find(p[0]))
        context = text[max(0, m.start() - 90): m.end()] + window[: window.find(tok)]
        if _NOT_THE_DEADLINE.search(context):
            continue
        (strong if _THE_DEADLINE.search(context) else generic).append(found)
    group = strong or generic
    return max(group) if group else None


def _positions(window: str) -> list[tuple[str, date]]:
    out: list[tuple[str, date]] = []
    for m in _NUM_DATE.finditer(window):
        try:
            out.append((m.group(0), date(int(m.group(3)), int(m.group(2)), int(m.group(1)))))
        except ValueError:
            continue
    for m in _TXT_DATE.finditer(window):
        try:
            out.append((m.group(0), date(int(m.group(3)), _IT_MONTHS.index(m.group(2).lower()) + 1, int(m.group(1)))))
        except ValueError:
            continue
    return out


# --- One state for every record -----------------------------------------------------
# aperto        shown in lists, counts and e-mails
# da_verificare kept out until the linked document has been read (tab "Da verificare")
# scaduto       deadline passed / document old: hidden (shown with "mostra scadute")
#
# PRE-GARA: any act that calls up a service; some noise is accepted, but its date must be
#   known: a deadline, or the document read ("recente"); read but no date found -> shown
#   flagged "data non verificata"; never read -> da_verificare.
# MANIFESTAZIONE / GARA: no noise accepted: a deadline written in the document itself
#   (read by the verification), later than the day of the check, or it stays da_verificare.
APERTO, DA_VERIFICARE, SCADUTO = "aperto", "da_verificare", "scaduto"


def record_state(
    category: str | None,
    scadenza: date | datetime | None,
    data_pubblicazione: date | datetime | None,
    url: str | None,
    verifica_esito: str | None,
    today: date | None = None,
) -> tuple[str, bool]:
    """(state, data_non_verificata). ``verifica_esito``: aperto | recente | chiuso |
    non_trovata | None (never read)."""
    today = today or today_utc()
    if verifica_esito == "chiuso":
        return SCADUTO, False
    deadline = _as_date(scadenza)
    if category in STRICT_CATEGORIES:
        if deadline is None:
            return DA_VERIFICARE, False
        if deadline < today:
            return SCADUTO, False
        return (APERTO, False) if verifica_esito == "aperto" else (DA_VERIFICARE, False)
    # pre-gara (or an unclassified record)
    if deadline is not None:
        return (APERTO, False) if deadline >= today else (SCADUTO, False)
    uy = url_year(url)
    if verifica_esito == "recente":
        return APERTO, False
    if uy is not None and uy < today.year - 1:
        return SCADUTO, False
    if verifica_esito == "non_trovata":
        return (APERTO, True) if is_actionable(None, data_pubblicazione, today) else (SCADUTO, False)
    return DA_VERIFICARE, False


def recent_date_in_text(text: str | None, today: date, *, head: int = 4000, max_age_days: int = MAX_AGE_DAYS) -> date | None:
    """Most recent past date written in the first ``head`` characters of a document (its
    title block: act date, publication date) when it falls in the window, else None."""
    ds = [d for d in dates_in_text((text or "")[:head]) if d <= today]
    if not ds:
        return None
    latest = max(ds)
    return latest if latest >= today - timedelta(days=max_age_days) else None
