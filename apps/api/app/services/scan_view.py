"""What the per-comune progress view shows for a scan run. Pure, tested."""
from __future__ import annotations

from datetime import datetime
from typing import Any

FINISHED = {"done", "error", "skipped"}
# A "running" run that has not written anything for this long was killed
# (worker restart, time limit): it is shown as interrupted, not as running forever.
STALE_AFTER_S = 600


def scan_summary(
    run: Any,
    items: list[Any],
    now: datetime,
    stale_after: int = STALE_AFTER_S,
    costs: dict | None = None,
    run_cost: float | None = None,
) -> dict:
    status = run.status
    if status == "running" and run.heartbeat_at is not None and (now - run.heartbeat_at).total_seconds() > stale_after:
        status = "interrupted"

    done = sum(1 for i in items if i.status in FINISHED)
    # In an interrupted run nothing is still running: a comune caught mid-way
    # was cut off, and is shown as such (it is read again on resume).
    cut_off = status == "interrupted"
    running = 0 if cut_off else sum(1 for i in items if i.status == "running")
    interrupted = sum(1 for i in items if i.status == "running") if cut_off else 0
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
        # An open comune lasts until "now" in a live run, or until the run's last
        # sign of life in an interrupted one (not until a moment hours later).
        return round(((i.ended_at or end) - i.started_at).total_seconds(), 1)

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
        "interrupted": interrupted,
        "queued": total - done - running - interrupted,
        "limit": run.sample_limit,
        "error": run.error,
        "cost_usd": round(run_cost, 4) if run_cost is not None else None,
        "claude": {
            "status": run.claude_status,
            "error": run.claude_error,
            "calls": calls,
            "call_errors": call_errors,
        },
        "items": [
            {
                "ente": i.ente,
                "status": "interrupted" if cut_off and i.status == "running" else i.status,
                "started_at": i.started_at,
                "ended_at": i.ended_at,
                "duration_s": seconds(i),
                "pages_read": i.pages_read,
                "pages_skipped": i.pages_skipped,
                "claude_calls": i.claude_calls,
                "claude_errors": i.claude_errors,
                "cost_usd": round(costs.get(getattr(i, "id", None), 0.0), 4) if costs is not None else None,
                "records_found": i.records_found,
                "deepest": i.deepest,
                "stopped_by": i.stopped_by,
                "error": i.error,
            }
            for i in ordered
        ],
    }
