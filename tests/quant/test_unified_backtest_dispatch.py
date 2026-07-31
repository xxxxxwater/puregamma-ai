from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.api.routers import backtest_lab
from packages.workers.tasks import execute_unified_backtest


def _unavailable_redis():
    raise ConnectionError("Redis is unavailable")


def test_backtest_dispatches_to_celery_when_redis_is_available(monkeypatch):
    queued: list[str] = []
    monkeypatch.setattr(backtest_lab, "get_settings", lambda: SimpleNamespace(app_environment="production"))
    monkeypatch.setattr("apps.api.redis_client.get_redis", lambda: SimpleNamespace(ping=lambda: True))
    monkeypatch.setattr(execute_unified_backtest, "delay", lambda run_id: queued.append(run_id))

    backtest_lab._dispatch_or_run(object(), "run-async")

    assert queued == ["run-async"]


def test_backtest_falls_back_to_sync_only_in_development(monkeypatch):
    executed: list[str] = []
    monkeypatch.setattr(backtest_lab, "get_settings", lambda: SimpleNamespace(app_environment="development"))
    monkeypatch.setattr("apps.api.redis_client.get_redis", _unavailable_redis)
    monkeypatch.setattr(
        "apps.api.services.unified_backtest_service.execute_unified_run",
        lambda _db, run_id: executed.append(run_id),
    )

    backtest_lab._dispatch_or_run(object(), "run-sync")

    assert executed == ["run-sync"]


def test_production_redis_failure_marks_the_run_failed_without_sync_execution(monkeypatch):
    failed: list[tuple[str, str]] = []
    monkeypatch.setattr(backtest_lab, "get_settings", lambda: SimpleNamespace(app_environment="production"))
    monkeypatch.setattr("apps.api.redis_client.get_redis", _unavailable_redis)
    monkeypatch.setattr(
        backtest_lab,
        "fail_unified_run",
        lambda _db, run_id, *, code, message: failed.append((run_id, code)),
    )

    with pytest.raises(backtest_lab.BacktestDispatchUnavailable):
        backtest_lab._dispatch_or_run(object(), "run-unavailable")

    assert failed == [("run-unavailable", "BACKTEST_QUEUE_UNAVAILABLE")]
