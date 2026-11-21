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
