from uuid import UUID

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/run-daily-monitor")
async def run_daily_monitor() -> dict:
    """Trigger the daily monitor pipeline (dispatches official + eproc tasks)."""
    from app.services.admin_service import dispatch_daily_monitor

    task_ids = dispatch_daily_monitor()
    return {"status": "dispatched", **task_ids}


@router.post("/retry-source/{source_id}")
async def retry_source(source_id: UUID) -> dict:
    """Re-run collection for a single source."""
    from app.services.admin_service import dispatch_collect_single_source

    task_id = dispatch_collect_single_source(source_id)
    if task_id is None:
        raise HTTPException(status_code=404, detail="Source not found or inactive")
    return {"status": "dispatched", "task_id": task_id, "source_id": str(source_id)}


@router.post("/normalize-records")
async def run_normalize_records() -> dict:
    """Trigger the raw → procurement normalization task."""
    from app.services.admin_service import dispatch_normalize_records

    task_id = dispatch_normalize_records()
    return {"status": "dispatched", "task_id": task_id}


@router.post("/score-and-dedupe")
async def run_score_and_dedupe() -> dict:
    """Trigger the dedup + commercial scoring pass."""
    from app.services.admin_service import dispatch_score_and_dedupe

    task_id = dispatch_score_and_dedupe()
    return {"status": "dispatched", "task_id": task_id}


@router.post("/rebuild-report/{report_date}")
async def rebuild_report(report_date: str) -> dict:
    """Trigger a regeneration of today's daily report (report_date is informational)."""
    from app.services.admin_service import dispatch_generate_daily_report

    task_id = dispatch_generate_daily_report()
    return {"status": "dispatched", "task_id": task_id, "report_date": report_date}


@router.post("/detect-anomalies")
async def run_detect_anomalies() -> dict:
    """Trigger anomaly detection pass."""
    from app.services.admin_service import dispatch_detect_anomalies

    task_id = dispatch_detect_anomalies()
    return {"status": "dispatched", "task_id": task_id}


@router.post("/run-backfill")
async def run_backfill(days: int = 7) -> dict:
    """Trigger a historical backfill (days must be one of 7, 14, 30)."""
    if days not in (7, 14, 30):
        raise HTTPException(status_code=400, detail="days must be 7, 14 or 30")
    from app.services.admin_service import dispatch_backfill

    task_id = dispatch_backfill(days)
    return {"status": "dispatched", "task_id": task_id, "window_days": days}
