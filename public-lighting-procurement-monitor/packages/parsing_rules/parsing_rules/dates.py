"""Date parsing helpers. Ported from scripts/pipeline.js:22-28."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

_IT_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?$")


def parse_italian_date(raw: str | None) -> datetime | None:
    """Parse dd/mm/yyyy, yyyy-mm-dd or ISO 8601. Returns UTC-aware datetime."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"n.d.", "nd", "na", "n/a"}:
        return None

    m = _IT_DATE.search(s)
    if m:
        day, month, year = map(int, m.groups())
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None

    if _ISO_DATE.match(s):
        try:
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None

    return None


def days_until(target: str | datetime | date | None, *, now: datetime | None = None) -> int | None:
    """Days between today (UTC) and target. Negative if target is in the past."""
    if target is None:
        return None
    if isinstance(target, str):
        parsed = parse_italian_date(target)
    elif isinstance(target, datetime):
        parsed = target if target.tzinfo else target.replace(tzinfo=timezone.utc)
    elif isinstance(target, date):
        parsed = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
    else:
        return None

    if parsed is None:
        return None

    reference = now or datetime.now(tz=timezone.utc)
    delta = parsed.date() - reference.date()
    return delta.days
