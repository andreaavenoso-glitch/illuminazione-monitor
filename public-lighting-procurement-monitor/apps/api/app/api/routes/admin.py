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
