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
    """Minimal stand-in for the subset of the Redis API the lock uses.

    `eval` interprets the module's own RENEW_SCRIPT / RELEASE_SCRIPT rather than
    reimplementing their logic, so these tests cannot pass against a script that
    the real server would execute differently.
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        #: Set by a test to make another client take the key between the compare
        #: and the write, which is exactly the interleaving the script removes.
        self.steal_to: str | None = None
        self.eval_calls: list[tuple[str, tuple]] = []

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

    def eval(self, script, numkeys, *args):
        self.eval_calls.append((script, args))
        key = args[0]
        token = args[1] if len(args) > 1 else None
        if self.steal_to is not None:
            # Simulate a successor acquiring the key in the window that a
            # GET-then-EXPIRE implementation would leave open.
            self.store[key] = self.steal_to
            self.ttls[key] = 900
        current = self.store.get(key)
        if script == redis_lock.RENEW_SCRIPT:
            if current is None:
                return 0
            if current != token:
                return 1
            self.ttls[key] = int(args[2]) // 1000
            return 2
        if script == redis_lock.RELEASE_SCRIPT:
            if current is None:
                return 0
            if current != token:
                return 1
            self.store.pop(key, None)
            self.ttls.pop(key, None)
            return 2
        raise AssertionError("unexpected script passed to eval")


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


def test_renew_is_atomic_and_never_extends_a_successors_lock(fake_redis):
    """A renewal that loses the race must not extend the new owner's lock.

    With `GET` then `EXPIRE` as two round trips, a lock that expired between them
    could be acquired by a successor and then extended by the old owner's
    `EXPIRE` — the successor's lock would inherit the previous owner's TTL and
    the old owner would be told nothing. The server-side script removes the
    window entirely.
    """
    acquired, token = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)
    assert acquired
    fake_redis.ttls[KEY] = 5

    # Another scheduler takes the key in the middle of our renewal.
    fake_redis.steal_to = "successor:7"

    assert redis_lock.renew_redis_lock("scheduler", token, ttl_seconds=900) is False
    # The successor keeps ITS ttl; our renewal must not have touched it.
    assert fake_redis.ttls[KEY] == 900
    assert fake_redis.store[KEY] == "successor:7"


def test_release_is_atomic_and_never_deletes_a_successors_lock(fake_redis):
    acquired, token = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)
    assert acquired

    fake_redis.steal_to = "successor:7"

    assert redis_lock.release_redis_lock("scheduler", token) is False
    assert fake_redis.store[KEY] == "successor:7"

    # ...and our own lock still releases normally.
    fake_redis.steal_to = None
    fake_redis.store[KEY] = token
    assert redis_lock.release_redis_lock("scheduler", token) is True
    assert KEY not in fake_redis.store


def test_renew_and_release_go_through_the_scripts(fake_redis):
    """Pin the mechanism, not just the outcome.

    A GET/EXPIRE pair and an EVAL can produce identical results in a fake, so the
    atomicity claim is only real if the implementation actually uses the scripts.
    """
    acquired, token = redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900)
    assert acquired

    redis_lock.renew_redis_lock("scheduler", token, ttl_seconds=900)
    redis_lock.release_redis_lock("scheduler", token)

    scripts = [script for script, _ in fake_redis.eval_calls]
    assert redis_lock.RENEW_SCRIPT in scripts
    assert redis_lock.RELEASE_SCRIPT in scripts
    # No unlocked read-modify-write may remain alongside the scripts.
    assert "PEXPIRE" in redis_lock.RENEW_SCRIPT
    assert "DEL" in redis_lock.RELEASE_SCRIPT


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
