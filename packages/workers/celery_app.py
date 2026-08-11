from __future__ import annotations

import logging

from celery import Celery
from celery.signals import task_failure, task_soft_time_limited

from apps.api.config import get_settings


settings = get_settings()
logger = logging.getLogger("puregamma.worker")

if settings.sentry_dsn:
    try:
        import sentry_sdk  # type: ignore[import-not-found]

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_environment,
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
        logger.info("Sentry error tracking enabled (worker)")
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.warning("Sentry initialization skipped (worker): %s", exc)


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


def _alert_ops(task_name: str, message: str, *, level: str = "warning") -> None:
    try:
        from apps.api.services.ops_alert import notify_ops

        notify_ops(f"[worker:{task_name}] {message}", level=level)
    except Exception:  # pragma: no cover - never break the worker on alerting
        logger.exception("ops_alert_failed task=%s", task_name)


@task_soft_time_limited.connect
def _on_task_soft_timeout(sender, task_id, **kwargs):
    _alert_ops(sender.name, f"task {task_id} hit soft time limit", level="error")


@task_failure.connect
def _on_task_failure(sender, task_id, exception, traceback, **kwargs):
    _alert_ops(sender.name, f"task {task_id} failed: {exception!r}", level="error")

