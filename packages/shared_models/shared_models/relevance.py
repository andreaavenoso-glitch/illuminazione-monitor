"""When a notice is still worth showing.

A deadline is binding: a notice whose deadline (``scadenza``) is before today is
over and is noise, whatever it is about. Without a deadline there is only the
publication date to go by, so very old notices (an "avviso" from two years ago
still sitting on an albo) are left out too. Pure functions.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

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
