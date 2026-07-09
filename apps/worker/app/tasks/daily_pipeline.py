"""Single entry point for the automatic daily pipeline.

Chains collect -> normalize -> score -> report -> anomalies as a strict
Celery chain, so each stage only starts once the previous one has actually
finished, instead of independent fixed-time cron entries that assumed every
stage would always complete inside its allotted window (a single collector
pass has taken 5-9+ minutes in practice; a bigger watchlist or a slow source
can blow past a 15/30-minute gap and leave the next stage working on a
partial dataset).
"""
from __future__ import annotations

from app.celery_app import celery_app
from app.tasks.collect_sources import collect_eproc_portals, collect_official_sources
from app.tasks.collect_watchlist import collect_watchlist_albo
from app.tasks.detect_anomalies import detect_anomalies_task
from app.tasks.generate_daily_report import generate_daily_report
from app.tasks.normalize_records import normalize_records
from app.tasks.score_and_dedupe import score_and_dedupe
from celery import chain


@celery_app.task(name="app.tasks.daily_pipeline.run_daily_pipeline")
def run_daily_pipeline() -> str:
    """Dispatch the full daily chain and return its AsyncResult id.

    Each step uses ``.si()`` (immutable signature) so a stage's return value
    is never passed as an argument to the next one -- these tasks take no
    input, they just need to run in order.
    """
    result = chain(
        collect_official_sources.si(),
        collect_eproc_portals.si(),
        collect_watchlist_albo.si(),
        normalize_records.si(),
        score_and_dedupe.si(),
        generate_daily_report.si(),
        detect_anomalies_task.si(),
    ).apply_async()
    return result.id
