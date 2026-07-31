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
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=540,
    task_time_limit=600,
    result_expires=3600,
)
