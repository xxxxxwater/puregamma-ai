from __future__ import annotations

from celery import Celery

from apps.api.config import get_settings


settings = get_settings()

celery_app = Celery(
    "puregamma",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["packages.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
