"""Raccolta mirata e stop della raccolta."""
from __future__ import annotations

from app.services.admin_service import region_scan_steps


def test_targeted_ids_go_to_the_collection_step_only():
    steps = region_scan_steps("Lombardia", None, None, ["a", "b"])
    assert steps[0][1]["item_ids"] == ["a", "b"]
    assert all("item_ids" not in kw for _, kw in steps[1:])


def test_slow_followers_respect_the_stop():
    kw = {n.rsplit(".", 1)[-1]: k for n, k in region_scan_steps("Puglia")}
    assert kw["collect_regional_sites"]["respect_stop"] is True
    assert kw["verify_region_records"]["respect_stop"] is True
    assert "respect_stop" not in kw["normalize_records"]  # what was collected is still processed


def test_stopped_is_a_known_status_in_the_progress_view():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.services.scan_view import scan_summary

    now = datetime.now(tz=UTC)
    run = SimpleNamespace(
        id="r", region="Puglia", status="stopped", started_at=now, ended_at=now, heartbeat_at=now, total=1,
        sample_limit=None, claude_status="ok", claude_error=None, error=None, stop_requested=True,
    )
    item = SimpleNamespace(
        id="i", item_id="w", ente="Comune di A", status="skipped", started_at=None, ended_at=now, error="raccolta fermata",
        pages_read=0, pages_skipped=0, claude_calls=0, claude_errors=0, records_found=0, deepest=0, stopped_by=None,
    )
    assert scan_summary(run, [item], now)["status"] == "stopped"
