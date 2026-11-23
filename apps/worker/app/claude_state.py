"""Whether Claude can be used right now, and the extraction mode.

``EXTRACTION_MODE``: ``auto`` (default) uses Claude and, when it is unavailable (no credit,
spending limit, no key), goes on with the free rules instead of stopping; ``claude``
never falls back (a refusal stops the scan, as before); ``rules`` never calls Claude.
After a fatal refusal in ``auto`` Claude is not tried again for ``RETRY_AFTER_S`` seconds,
so a topped-up account is picked up again without a restart.
"""
from __future__ import annotations

import time

from app.config import WorkerSettings

RETRY_AFTER_S = 600.0
_down_until = 0.0
_last_error: str | None = None


def mode(settings: WorkerSettings) -> str:
    m = (settings.extraction_mode or "auto").strip().lower()
    return m if m in ("auto", "claude", "rules") else "auto"


def mark_down(error: str, *, seconds: float = RETRY_AFTER_S) -> None:
    global _down_until, _last_error
    _down_until = time.monotonic() + seconds
    _last_error = error


def reset() -> None:
    global _down_until, _last_error
    _down_until = 0.0
    _last_error = None


def last_error() -> str | None:
    return _last_error


def is_down() -> bool:
    return time.monotonic() < _down_until


def use_claude(settings: WorkerSettings) -> bool:
    m = mode(settings)
    if m == "rules":
        return False
    if m == "claude":
        return True
    return bool(settings.anthropic_api_key) and not is_down()


def can_fall_back(settings: WorkerSettings) -> bool:
    return mode(settings) == "auto"
