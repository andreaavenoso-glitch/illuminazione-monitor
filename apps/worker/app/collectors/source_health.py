"""Per-source health bookkeeping for the watchlist scan.

A scan that reads nothing used to look identical to one that read a page and
found nothing relevant -- both just left ``last_scan_at`` updated -- so dead
addresses (404, DNS, SSL, blocked) went unnoticed until someone read worker
logs. This keeps three facts on each watchlist item: when its pages were last
actually readable, how many scans in a row weren't, and the last error kind.

Pure on purpose (no DB, no network) so it's unit-testable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol


class _HealthFields(Protocol):
    last_success_at: datetime | None
    consecutive_failures: int
    last_error: str | None


def apply_scan_outcome(
    item: _HealthFields,
    *,
    now: datetime,
    ok: bool,
    error: str | None = None,
) -> None:
    """Record whether this scan could read any of the item's pages.

    ``ok`` means at least one primary URL returned content (finding nothing
    relevant on it still counts as ok: the source is healthy, it just had
    nothing to report). Otherwise the failure streak grows and the error
    kind of the first failing URL is kept.
    """
    if ok:
        item.last_success_at = now
        item.consecutive_failures = 0
        item.last_error = None
        return
    item.consecutive_failures = (item.consecutive_failures or 0) + 1
    item.last_error = error or "empty"
