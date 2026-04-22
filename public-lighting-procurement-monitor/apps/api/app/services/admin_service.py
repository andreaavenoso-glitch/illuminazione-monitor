from uuid import UUID

from celery import Celery

from app.core.config import get_settings


def _celery_app() -> Celery:
    settings = get_settings()
    return Celery(
        "lighting_monitor",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )


def dispatch_daily_monitor() -> str:
    app = _celery_app()
    result = app.send_task("app.tasks.collect_sources.collect_official_sources")
    return str(result.id)


def dispatch_collect_single_source(source_id: UUID) -> str | None:
    app = _celery_app()
    result = app.send_task(
        "app.tasks.collect_sources.collect_single_source",
        kwargs={"source_id": str(source_id)},
    )
    return str(result.id)
