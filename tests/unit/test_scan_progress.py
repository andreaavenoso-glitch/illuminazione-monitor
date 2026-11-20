"""Per-comune progress of a scan: what the worker records and what the view shows."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.services.scan_view import scan_summary
from app.tasks.collect_watchlist import item_progress, merge_stats

T0 = datetime(2026, 11, 18, 18, 0, tzinfo=UTC)


def _item(ente, status, *, start=None, end=None, **kw):
    base = {
        "ente": ente, "status": status,
        "started_at": T0 + timedelta(seconds=start) if start is not None else None,
        "ended_at": T0 + timedelta(seconds=end) if end is not None else None,
        "pages_read": 0, "pages_skipped": 0, "claude_calls": 0, "claude_errors": 0,
        "records_found": 0, "deepest": 0, "stopped_by": None, "error": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _run(**kw):
    base = {
        "id": "r1", "region": "Puglia", "status": "running", "started_at": T0, "ended_at": None,
        "heartbeat_at": T0 + timedelta(seconds=100), "sample_limit": None, "error": None,
        "claude_status": "unused", "claude_error": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


class TestWorkerCounters:
    def test_merge_sums_counts_and_keeps_the_deepest(self) -> None:
        total = Counter({"pages_read": 10, "max_depth_reached": 3})
        merge_stats(total, Counter({"pages_read": 5, "max_depth_reached": 2, "claude_errors": 1}))
        merge_stats(total, Counter({"max_depth_reached": 5}))
        assert total["pages_read"] == 15 and total["claude_errors"] == 1 and total["max_depth_reached"] == 5

    def test_item_progress_from_a_comune_counters(self) -> None:
        local = Counter({
            "pages_read": 20, "pages_skipped_no_keywords": 14, "pages_unchanged": 2, "pages_duplicate_content": 1,
            "pages_to_claude_compact": 2, "pages_to_claude_full": 1, "claude_errors": 0,
            "records_found": 3, "max_depth_reached": 4, "crawl_stopped_by_exhausted": 1,
        })
        assert item_progress(local) == {
            "pages_read": 20, "pages_skipped": 17, "claude_calls": 3, "claude_errors": 0,
            "records_found": 3, "deepest": 4, "stopped_by": "exhausted",
        }

    def test_item_progress_of_an_untouched_comune(self) -> None:
        p = item_progress(Counter())
        assert p["claude_calls"] == 0 and p["stopped_by"] is None and p["pages_read"] == 0


class TestScanSummary:
    def test_counts_progress_and_eta(self) -> None:
        items = [
            _item("A", "done", start=0, end=40, claude_calls=1),
            _item("B", "done", start=0, end=50),
            _item("C", "running", start=45),
            _item("D", "queued"),
        ]
        s = scan_summary(_run(), items, T0 + timedelta(seconds=100))
        assert (s["total"], s["done"], s["running"], s["queued"], s["errors"]) == (4, 2, 1, 1, 0)
        assert s["elapsed_s"] == 100
        assert s["eta_s"] == 100  # 2 left at 2 per 100 s
        assert s["claude"]["calls"] == 1

    def test_order_is_by_start_with_queued_last(self) -> None:
        items = [_item("Z", "queued"), _item("B", "done", start=20, end=30), _item("A", "done", start=5, end=9)]
        assert [i["ente"] for i in scan_summary(_run(), items, T0 + timedelta(seconds=60))["items"]] == ["A", "B", "Z"]

    def test_durations(self) -> None:
        items = [_item("A", "done", start=10, end=70), _item("B", "running", start=30), _item("C", "queued")]
        by = {i["ente"]: i["duration_s"] for i in scan_summary(_run(), items, T0 + timedelta(seconds=90))["items"]}
        assert by == {"A": 60.0, "B": 60.0, "C": None}

    def test_finished_run_has_no_eta_and_uses_its_end_time(self) -> None:
        run = _run(status="done", ended_at=T0 + timedelta(seconds=200))
        s = scan_summary(run, [_item("A", "done", start=0, end=190)], T0 + timedelta(hours=3))
        assert s["status"] == "done" and s["eta_s"] is None and s["elapsed_s"] == 200

    def test_a_run_that_stopped_writing_is_interrupted(self) -> None:
        run = _run(heartbeat_at=T0 + timedelta(seconds=30))
        s = scan_summary(run, [_item("A", "running", start=0)], T0 + timedelta(minutes=30))
        assert s["status"] == "interrupted" and s["eta_s"] is None
        assert s["elapsed_s"] == 30  # measured up to its last sign of life, not up to now
        # the comune caught mid-way is "interrupted", not still "running", and its
        # duration stops at the run's last sign of life
        assert (s["running"], s["interrupted"]) == (0, 1)
        assert s["items"][0]["status"] == "interrupted" and s["items"][0]["duration_s"] == 30.0

    def test_claude_down_is_reported_with_its_reason(self) -> None:
        run = _run(status="failed", ended_at=T0 + timedelta(seconds=50), claude_status="down",
                   claude_error="You have reached your specified API usage limits")
        items = [_item("A", "error", start=0, end=20, error="Claude non disponibile: ..."),
                 _item("B", "skipped", error="Claude non disponibile")]
        s = scan_summary(run, items, T0 + timedelta(seconds=60))
        assert s["claude"]["status"] == "down" and "usage limits" in s["claude"]["error"]
        assert (s["errors"], s["done"]) == (1, 2)


class TestResume:
    def _items(self):
        now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
        mk = lambda n, ago: SimpleNamespace(n=n, last_scan_at=None if ago is None else now - timedelta(hours=ago))  # noqa: E731
        return now, [mk("never", None), mk("1h", 1), mk("23h", 23), mk("25h", 25), mk("3d", 72)]

    def test_resume_skips_what_was_read_recently(self) -> None:
        from app.tasks.collect_watchlist import filter_stale

        now, items = self._items()
        assert [i.n for i in filter_stale(items, 24, now)] == ["never", "25h", "3d"]

    def test_no_window_keeps_everything(self) -> None:
        from app.tasks.collect_watchlist import filter_stale

        now, items = self._items()
        assert filter_stale(items, None, now) == items


@pytest.mark.asyncio
class TestCheckpointer:
    async def test_runs_every_n_finished_comuni(self) -> None:
        from app.tasks.collect_watchlist import Checkpointer

        calls = []

        async def action():
            calls.append(1)

        cp = Checkpointer(3, action)
        for _ in range(8):
            await cp.tick()
        assert len(calls) == 2  # after the 3rd and the 6th

    async def test_a_failing_action_never_fails_the_scan(self) -> None:
        from app.tasks.collect_watchlist import Checkpointer

        async def boom():
            raise RuntimeError("db hiccup")

        cp = Checkpointer(1, boom)
        await cp.tick()
        await cp.tick()  # still usable after a failure
        assert cp.finished == 2

    async def test_never_two_at_once(self) -> None:
        import asyncio

        from app.tasks.collect_watchlist import Checkpointer

        running = peak = total = 0

        async def action():
            nonlocal running, peak, total
            running += 1
            peak = max(peak, running)
            total += 1
            await asyncio.sleep(0.02)
            running -= 1

        cp = Checkpointer(1, action)
        await asyncio.gather(*(cp.tick() for _ in range(6)))
        assert peak == 1 and 1 <= total <= 6  # overlapping ticks are skipped, not queued


def test_process_steps_normalize_then_score() -> None:
    from app.services.admin_service import process_steps

    assert [n.rsplit(".", 1)[-1] for n, _ in process_steps()] == ["normalize_records", "score_and_dedupe"]
