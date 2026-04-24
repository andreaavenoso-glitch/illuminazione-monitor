"""Pipeline stage 5: run the anomaly detector and persist Alert rows.

Uses an ``alert_key`` stored in the description field to deduplicate against
already-open alerts. Runs daily at 07:30 UTC (after report generation).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.celery_app import celery_app
from app.db import SessionLocal
from app.domain.anomaly_detection import AnomalyContext, detect_anomalies
from shared_models import Alert, JobRun, ProcurementRecord, RecordEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

KEY_PREFIX = "[key:"


def _encode_description(alert_key: str, description: str) -> str:
    return f"{KEY_PREFIX}{alert_key}] {description}"


def _extract_key(description: str) -> str | None:
    if not description.startswith(KEY_PREFIX):
        return None
    end = description.find("]")
    if end <= len(KEY_PREFIX):
        return None
    return description[len(KEY_PREFIX) : end]


async def _load_context(session: AsyncSession) -> AnomalyContext:
    records = list((await session.execute(select(ProcurementRecord))).scalars().all())
    events = list((await session.execute(select(RecordEvent))).scalars().all())
    open_alerts = list(
        (await session.execute(select(Alert).where(Alert.is_open.is_(True))))
        .scalars()
        .all()
    )
    open_keys = {k for a in open_alerts if (k := _extract_key(a.description or "")) is not None}
    return AnomalyContext(records=records, events=events, open_alert_keys=open_keys)


async def _run() -> dict[str, int]:
    async with SessionLocal() as session:
        job = JobRun(job_name="detect_anomalies", status="running")
        session.add(job)
        await session.flush()

        now = datetime.now(tz=UTC)
        try:
            ctx = await _load_context(session)
            candidates = detect_anomalies(ctx, now=now)
            opened = 0
            from uuid import UUID

            for c in candidates:
                alert = Alert(
                    procurement_record_id=(
                        UUID(c.procurement_record_id) if c.procurement_record_id else None
                    ),
                    alert_type=c.alert_type,
                    severity=c.severity,
                    description=_encode_description(c.alert_key, c.description),
                )
                session.add(alert)
                opened += 1

            job.records_found = len(candidates)
            job.records_valid = opened
            job.status = "success"
        except Exception as exc:  # noqa: BLE001
            log.exception("detect_anomalies.crashed", extra={"err": str(exc)})
            job.status = "failed"
            job.error_message = f"{type(exc).__name__}: {exc}"

        job.ended_at = datetime.now(tz=UTC)
        await session.commit()
        return {
            "candidates": job.records_found,
            "alerts_opened": job.records_valid,
            "status": job.status,
        }


@celery_app.task(name="app.tasks.detect_anomalies.detect_anomalies")
def detect_anomalies_task() -> dict[str, int]:
    return asyncio.run(_run())
