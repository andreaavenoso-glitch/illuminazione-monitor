"""The user's "Ferma raccolta": checks the scan's stop flag (set through the API)."""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from app.db import SessionLocal
from shared_models import ScanRun
from shared_models.regions import normalize_region
from sqlalchemy import select

log = logging.getLogger(__name__)
_cache: dict[object, tuple[float, bool]] = {}
TTL_S = 2.0


async def run_stopped(run_id) -> bool:
    """Has the user asked to stop this run? Read at most every 2 seconds (one query per comune otherwise)."""
    now = time.monotonic()
    hit = _cache.get(run_id)
    if hit and now - hit[0] < TTL_S:
        return hit[1]
    try:
        async with SessionLocal() as s:
            value = bool(await s.scalar(select(ScanRun.stop_requested).where(ScanRun.id == run_id)))
    except Exception:  # noqa: BLE001
        log.exception("stop.read_failed")
        return False
    _cache[run_id] = (now, value)
    return value


async def region_stopped(region: str | None, *, within_hours: float = 12) -> bool:
    """Was the latest run of this region stopped by the user? The slow steps that follow a collection
    (regional sites, verification) are skipped then; normalisation still runs on what was collected."""
    if not region:
        return False
    try:
        async with SessionLocal() as s:
            run = (
                await s.execute(
                    select(ScanRun).where(ScanRun.region == normalize_region(region)).order_by(ScanRun.started_at.desc()).limit(1)
                )
            ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        return False
    if run is None or not run.stop_requested:
        return False
    return datetime.now(tz=UTC) - run.started_at < timedelta(hours=within_hours)
