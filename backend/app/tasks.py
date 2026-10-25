from celery import Celery
from celery.schedules import crontab

from app.config import get_settings
from app.ingestion import sync_january_data

celery_app = Celery("wind_insights", broker=get_settings().redis_url)
celery_app.conf.update(
    result_backend=get_settings().redis_url,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "refresh-january-elexon-data-daily": {
            "task": "app.tasks.refresh_january_data",
            "schedule": crontab(hour=2, minute=0),
        }
    },
)


@celery_app.task(
    bind=True,
    name="app.tasks.refresh_january_data",
    autoretry_for=(OSError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def refresh_january_data(self) -> dict[str, int]:
    return sync_january_data()
