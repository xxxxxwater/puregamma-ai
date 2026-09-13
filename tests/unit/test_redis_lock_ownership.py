"""Distributed lock semantics for the single-scheduler invariant.

Three defects found while investigating a scheduler that would not start:

1. `renew_redis_lock` did not exist. The scheduler's "keep the lock alive" job
   called `acquire_redis_lock` again, which is `SET NX` against a key the process
   already holds — it returns False and leaves the TTL untouched, so the lock was
   never actually kept alive and its docstring was wrong.
2. `release_redis_lock` deleted the key unconditionally, so an instance shutting
   down could delete a successor's lock.
3. The value was the literal "1", so an operator could not tell whether the
   holder was still alive — which is why stale locks had to be inferred from
   timing during a deployment.

These tests pin the corrected behaviour with a fake Redis client, so they run
without a live Redis.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from packages.workers import redis_lock


class FakeRedis:
    """Minimal stand-in for the subset of the Redis API the lock uses."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def get(self, key):
        return self.store.get(key)

    def expire(self, key, ttl):
        if key not in self.store:
            return False
        self.ttls[key] = ttl
        return True

    def delete(self, key):
        self.store.pop(key, None)
        self.ttls.pop(key, None)
        return 1

    def ttl(self, key):
        return self.ttls.get(key, -2) if key in self.store else -2


@pytest.fixture()
def fake_redis(monkeypatch):
    client = FakeRedis()
    monkeypatch.setitem(sys.modules, "apps.api.redis_client", SimpleNamespace(get_redis=lambda: client))
    return client


KEY = "pg:lock:scheduler"


def test_acquire_records_an_identifiable_owner(fake_redis):
    acquired, token = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)

    assert acquired is True
    # The value answers "who holds this?", not just "is it held?".
    assert token and token != "1"
    assert ":" in token
    assert fake_redis.store[KEY] == token
    assert fake_redis.ttls[KEY] == 900


def test_second_instance_cannot_acquire_or_steal(fake_redis):
    first_ok, first_token = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)
    second_ok, second_token = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900, token="other-host:999")

    assert first_ok is True
    assert second_ok is False
    assert second_token is None
    assert fake_redis.store[KEY] == first_token


def test_renew_extends_the_ttl_for_the_owner(fake_redis):
    acquired, token = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)
    assert acquired

    # Simulate the TTL having run down, as a long-running scheduler would see.
    fake_redis.ttls[KEY] = 12
    assert redis_lock.renew_redis_lock("scheduler", token, ttl_seconds=900) is True
    assert fake_redis.ttls[KEY] == 900


def test_renew_refuses_a_foreign_token(fake_redis):
    acquired, _ = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)
    assert acquired
    fake_redis.ttls[KEY] = 12

    assert redis_lock.renew_redis_lock("scheduler", "someone-else:1", ttl_seconds=900) is False
    # The foreign caller must not have changed anything.
    assert fake_redis.ttls[KEY] == 12
    assert fake_redis.store[KEY] != "someone-else:1"


def test_renew_returns_false_when_the_lock_is_gone(fake_redis):
    """A lock that expired must not be revived by the owner's renewal job."""
    assert redis_lock.renew_redis_lock("scheduler", "ghost:1", ttl_seconds=900) is False
    assert KEY not in fake_redis.store


def test_release_only_removes_our_own_lock(fake_redis):
    acquired, token = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)
    assert acquired

    # A successor taking over after a TTL expiry must survive our shutdown.
    fake_redis.store[KEY] = "successor:42"
    assert redis_lock.release_redis_lock("scheduler", token) is False
    assert fake_redis.store[KEY] == "successor:42"

    # ...and our own lock is released normally.
    fake_redis.store[KEY] = token
    assert redis_lock.release_redis_lock("scheduler", token) is True
    assert KEY not in fake_redis.store


def test_tokenless_release_keeps_legacy_behaviour(fake_redis):
    redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)

    assert redis_lock.release_redis_lock("scheduler") is True
    assert KEY not in fake_redis.store


def test_status_reports_the_holder_for_operators(fake_redis):
    acquired, token = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)
    assert acquired

    status = redis_lock.lock_status("scheduler")

    assert status["held"] is True
    assert status["holder"] == token
    assert status["ttl_seconds"] == 900
    assert status["key"] == KEY


def test_status_of_an_unheld_lock(fake_redis):
    status = redis_lock.lock_status("scheduler")

    assert status["held"] is False
    assert status["holder"] is None
    assert status["ttl_seconds"] is None


def test_redis_outage_fails_open_and_still_returns_a_token(monkeypatch):
    """Liveness wins when Redis is down; the caller still gets a usable token."""
    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setitem(sys.modules, "apps.api.redis_client", SimpleNamespace(get_redis=boom))

    acquired, token = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)

    assert acquired is True
    assert token  # releasing a fail-open acquire must not blow up
    assert redis_lock.release_redis_lock("scheduler", token) is False


def test_scheduler_renews_instead_of_reacquiring():
    """The renewal job must call renew, not acquire.

    Pins the actual defect: `acquire` is SET NX, so using it to renew silently
    left the TTL untouched while the docstring claimed the lock was kept alive.
    """
    import inspect

    from packages.workers import scheduler as scheduler_module

    source = inspect.getsource(scheduler_module.main)
    assert "renew_redis_lock" in source
    assert "LOCK_HOLDER_TTL_SECONDS" in source
    # The renewal job must receive the token, otherwise renew cannot prove ownership.
    assert "args=[\"scheduler\", token]" in source
    # A bare `acquire_redis_lock("scheduler")` used as the renewal target would
    # re-introduce the bug, so the acquire call must unpack the tuple.
    assert "acquired, token = acquire_redis_lock" in source
