"""Pipeline stage 4: generate the daily report.

Pulls today's procurement_records, the sources, the last 24h of job_runs and
open alerts; feeds them to app.domain.reporting.build_daily_report; upserts
the result into the ``daily_reports`` table. Runs at 07:00 UTC.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.celery_app import celery_app
from app.db import SessionLocal
from app.domain.reporting import ReportContext, build_daily_report
from shared_models import (
    Alert,
    DailyReport,
    JobRun,
    ProcurementRecord,
    Source,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


async def _load_context(session: AsyncSession, *, today: datetime) -> ReportContext:
    twenty_four_h_ago = today - timedelta(hours=24)

    records_stmt = select(ProcurementRecord)
    records = list((await session.execute(records_stmt)).scalars().all())

    sources_stmt = select(Source)
    sources = list((await session.execute(sources_stmt)).scalars().all())

    runs_stmt = (
        select(JobRun)
        .where(JobRun.started_at >= twenty_four_h_ago)
        .order_by(JobRun.started_at.asc())
    )
    job_runs = list((await session.execute(runs_stmt)).scalars().all())

    alerts_stmt = select(Alert).where(Alert.is_open.is_(True))
    alerts = list((await session.execute(alerts_stmt)).scalars().all())

    return ReportContext(records=records, sources=sources, job_runs=job_runs, alerts=alerts)


async def _run() -> dict[str, int]:
    async with SessionLocal() as session:
        job = JobRun(job_name="generate_daily_report", status="running")
        session.add(job)
        await session.flush()

        now = datetime.now(tz=UTC)
        try:
            ctx = await _load_context(session, today=now)
            report = build_daily_report(ctx, today=now.date(), now=now)

            existing_stmt = select(DailyReport).where(
                DailyReport.report_date == report.report_date
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            payload = report.to_json()
            totals = {
                "total_new": report.kpi["total_new"],
                "total_updates": report.kpi["total_updates"],
                "total_pregara": report.kpi["total_pregara"],
                "total_sources_ok": report.kpi["total_sources_ok"],
            }
            if existing is None:
                session.add(
                    DailyReport(
                        report_date=report.report_date,
                        report_json=payload,
                        total_new=totals["total_new"],
                        total_updates=totals["total_updates"],
                        total_pregara=totals["total_pregara"],
                        total_new_sources=totals["total_sources_ok"],
                    )
                )
            else:
                existing.report_json = payload
                existing.total_new = totals["total_new"]
                existing.total_updates = totals["total_updates"]
                existing.total_pregara = totals["total_pregara"]
                existing.total_new_sources = totals["total_sources_ok"]

            job.records_found = len(ctx.records)
            job.records_valid = (
                report.kpi["total_new"]
                + report.kpi["total_updates"]
                + report.kpi["total_pregara"]
            )
            job.status = "success"
        except Exception as exc:  # noqa: BLE001
            log.exception("generate_daily_report.crashed", extra={"err": str(exc)})
            job.error_message = f"{type(exc).__name__}: {exc}"
            job.status = "failed"

        job.ended_at = datetime.now(tz=UTC)
        await session.commit()
        return {
            "records_found": job.records_found,
            "records_valid": job.records_valid,
            "status": job.status,
        }


@celery_app.task(name="app.tasks.generate_daily_report.generate_daily_report")
def generate_daily_report() -> dict[str, int]:
    return asyncio.run(_run())
