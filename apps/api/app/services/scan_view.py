"""What the per-comune progress view shows for a scan run. Pure, tested."""
from __future__ import annotations

from datetime import datetime
from typing import Any

FINISHED = {"done", "error", "skipped"}
# A "running" run that has not written anything for this long was killed
# (worker restart, time limit): it is shown as interrupted, not as running forever.
STALE_AFTER_S = 600


def scan_summary(run: Any, items: list[Any], now: datetime, stale_after: int = STALE_AFTER_S) -> dict:
    status = run.status
    if status == "running" and run.heartbeat_at is not None and (now - run.heartbeat_at).total_seconds() > stale_after:
        status = "interrupted"

    done = sum(1 for i in items if i.status in FINISHED)
    running = sum(1 for i in items if i.status == "running")
    errors = sum(1 for i in items if i.status == "error")
    total = len(items)
    end = run.ended_at or (run.heartbeat_at if status == "interrupted" and run.heartbeat_at else now)
    elapsed = max(0.0, (end - run.started_at).total_seconds())

    eta = None
    if status == "running" and done > 0 and elapsed > 0:
        eta = round((total - done) / (done / elapsed))

    calls = sum(i.claude_calls for i in items)
    call_errors = sum(i.claude_errors for i in items)
    ordered = sorted(items, key=lambda i: (i.started_at is None, i.started_at or now, i.ente))

    def seconds(i: Any) -> float | None:
        if i.started_at is None:
            return None
        return round(((i.ended_at or now) - i.started_at).total_seconds(), 1)

    return {
        "id": str(run.id),
        "region": run.region,
        "status": status,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "elapsed_s": round(elapsed),
        "eta_s": eta,
        "total": total,
        "done": done,
        "running": running,
        "errors": errors,
        "queued": total - done - running,
        "limit": run.sample_limit,
        "error": run.error,
        "claude": {
            "status": run.claude_status,
            "error": run.claude_error,
            "calls": calls,
            "call_errors": call_errors,
        },
        "items": [
            {
                "ente": i.ente,
                "status": i.status,
                "started_at": i.started_at,
                "ended_at": i.ended_at,
                "duration_s": seconds(i),
                "pages_read": i.pages_read,
                "pages_skipped": i.pages_skipped,
                "claude_calls": i.claude_calls,
                "claude_errors": i.claude_errors,
                "records_found": i.records_found,
                "deepest": i.deepest,
                "stopped_by": i.stopped_by,
                "error": i.error,
            }
            for i in ordered
        ],
    }
