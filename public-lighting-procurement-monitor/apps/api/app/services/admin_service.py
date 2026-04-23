from uuid import UUID

from app.core.config import get_settings
from celery import Celery


def _celery_app() -> Celery:
    settings = get_settings()
    return Celery(
        "lighting_monitor",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )


def dispatch_daily_monitor() -> dict[str, str]:
    app = _celery_app()
    official = app.send_task("app.tasks.collect_sources.collect_official_sources")
    eproc = app.send_task("app.tasks.collect_sources.collect_eproc_portals")
    return {"official_task_id": str(official.id), "eproc_task_id": str(eproc.id)}


def dispatch_collect_single_source(source_id: UUID) -> str | None:
    app = _celery_app()
    result = app.send_task(
        "app.tasks.collect_sources.collect_single_source",
        kwargs={"source_id": str(source_id)},
    )
    return str(result.id)


def dispatch_normalize_records() -> str:
    app = _celery_app()
    result = app.send_task("app.tasks.normalize_records.normalize_records")
    return str(result.id)


def dispatch_score_and_dedupe() -> str:
    app = _celery_app()
    result = app.send_task("app.tasks.score_and_dedupe.score_and_dedupe")
    return str(result.id)


def dispatch_generate_daily_report() -> str:
    app = _celery_app()
    result = app.send_task("app.tasks.generate_daily_report.generate_daily_report")
    return str(result.id)


def dispatch_ingest_document(*, record_id: UUID, url: str, filename: str | None) -> str:
    app = _celery_app()
    result = app.send_task(
        "app.tasks.ingest_documents.ingest_document",
        kwargs={
            "record_id": str(record_id),
            "url": url,
            "filename": filename,
        },
    )
    return str(result.id)
