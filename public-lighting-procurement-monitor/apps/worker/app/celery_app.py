from app.config import get_worker_settings
from celery import Celery
from celery.schedules import crontab

settings = get_worker_settings()

celery_app = Celery(
    "lighting_monitor",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.collect_sources",
        "app.tasks.normalize_records",
    ],
)

celery_app.conf.update(
    timezone=settings.celery_timezone,
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    worker_max_tasks_per_child=100,
)

celery_app.conf.beat_schedule = {
    "collect-official-sources-daily": {
        "task": "app.tasks.collect_sources.collect_official_sources",
        "schedule": crontab(hour=5, minute=0),
    },
    "collect-eproc-portals-daily": {
        "task": "app.tasks.collect_sources.collect_eproc_portals",
        "schedule": crontab(hour=5, minute=30),
    },
    "normalize-records-daily": {
        "task": "app.tasks.normalize_records.normalize_records",
        "schedule": crontab(hour=6, minute=0),
    },
}
