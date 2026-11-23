"""Stato live di Claude: sonda solo quando e' giu', al massimo ogni 90 secondi."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api.routes.claude_status import should_probe

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def test_probe_only_while_down_and_throttled():
    assert not should_probe(True, NOW - timedelta(hours=1), NOW)   # works: nothing spent
    assert not should_probe(None, None, NOW)                       # unknown: nothing spent
    assert should_probe(False, NOW - timedelta(seconds=120), NOW)  # down and not probed lately
    assert not should_probe(False, NOW - timedelta(seconds=30), NOW)
    assert should_probe(False, None, NOW)
