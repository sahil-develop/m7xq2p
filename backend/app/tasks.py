import httpx
from celery import Celery
from celery.schedules import crontab

from app.config import get_settings
from app.ingestion import sync_january_data

_redis_url = get_settings().redis_url or "redis://localhost:6379/0"

celery_app = Celery("wind_insights", broker=_redis_url, backend=_redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=24 * 3600,
    timezone="UTC",
    enable_utc=True,
    # Re-deliver the task if a worker dies mid-sync; the sync is idempotent.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Elexon occasionally revises settlement data; a nightly refresh picks that up.
        "refresh-january-elexon-data-nightly": {
            "task": "app.tasks.refresh_january_data",
            "schedule": crontab(hour=2, minute=0),
        }
    },
)


@celery_app.task(
    name="app.tasks.refresh_january_data",
    autoretry_for=(httpx.TransportError, httpx.HTTPStatusError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 5},
)
def refresh_january_data() -> dict[str, int]:
    return sync_january_data()
