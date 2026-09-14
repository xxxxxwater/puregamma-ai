"""The scheduler's single-instance lock: renewal, and recovering from its own death.

Why this exists: after a promote the scheduler restart-looped for fifteen minutes
and then for longer, printing only "another scheduler instance holds
pg:lock:scheduler". The lock names a container that no longer exists, and nothing
in the code could tell that apart from a genuinely live sibling — so a crashed
scheduler could not start again until the holder TTL ran out, twice over.

These tests drive `main()` against an in-memory Redis stand-in so the takeover
decision is exercised rather than described.
"""
from __future__ import annotations

import pytest

from packages.workers import redis_lock, scheduler as scheduler_module


class FakeRedis:
    """Enough of the Redis API for the lock: SET NX EX, GET, DEL, EVAL(PEXPIRE)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl_ms: dict[str, int] = {}
        self.evals: list[tuple] = []

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.ttl_ms[key] = int(ex) * 1000
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.ttl_ms.pop(key, None)
        return 1 if self.store.pop(key, None) is not None else 0

    def eval(self, script, numkeys, key, *args):
        # Only RENEW_SCRIPT and RELEASE_SCRIPT are used, and both begin with GET.
        current = self.store.get(key)
        self.evals.append((script.strip().splitlines()[1].strip(), key, args))
        if current is None:
            return 0
        if current != args[0]:
            return 1
        if "PEXPIRE" in script:
            self.ttl_ms[key] = int(args[1])
            return 2
        self.delete(key)
        return 2

    def ttl(self, key):
        return -2 if key not in self.store else self.ttl_ms.get(key, 0) // 1000


@pytest.fixture()
def fake_redis(monkeypatch):
    client = FakeRedis()
    # redis_lock imports get_redis lazily inside each call, so patching the
    # module attribute is enough.
    import apps.api.redis_client as redis_client

    monkeypatch.setattr(redis_client, "get_redis", lambda: client)
    return client


def test_renewal_extends_the_ttl_the_ttl_key_is_actually_set(fake_redis):
    """The renewal job is the only thing keeping the lock alive; prove it moves."""
    key = redis_lock.lock_key("scheduler")
    assert redis_lock.acquire_redis_lock("scheduler", ttl_seconds=900, token="me:1") == (True, "me:1")
    assert fake_redis.ttl_ms[key] == 900_000

    # Simulate most of the TTL having elapsed, then renew.
    fake_redis.ttl_ms[key] = 60_000
    assert redis_lock.renew_redis_lock("scheduler", "me:1", ttl_seconds=900) is True
    assert fake_redis.ttl_ms[key] == 900_000, "renewal must extend the stored TTL"

    # A different owner must not be able to extend or steal it.
    assert redis_lock.renew_redis_lock("scheduler", "someone-else:1", ttl_seconds=900) is False
    assert redis_lock.release_redis_lock("scheduler", "someone-else:1") is False
    assert fake_redis.get(key) == "me:1"
    assert redis_lock.release_redis_lock("scheduler", "me:1") is True
    assert fake_redis.get(key) is None


def test_a_dead_holder_can_be_replaced_by_the_container_that_reuses_its_name(fake_redis, monkeypatch, caplog):
    """The recovery path this release adds.

    A crashed scheduler leaves the lock naming "<container-id>:1". When the same
    container restarts, its hostname is unchanged, so the stale holder is provably
    itself and it may take the lock back instead of waiting out the TTL.
    """
    monkeypatch.setattr(redis_lock, "instance_identity", lambda: "schedulerhost:1")
    key = redis_lock.lock_key("scheduler")
    fake_redis.set(key, "schedulerhost:1", nx=True, ex=900)  # left behind by the dead run

    started: list[bool] = []
    monkeypatch.setattr(scheduler_module, "build_scheduler", lambda: _StubScheduler(started))

    with caplog.at_level("WARNING"):
        scheduler_module.main()
    assert started == [True], "the scheduler should have started on its own lock"
    assert any("reclaimed" in record.message or "reclaimed" in record.getMessage() for record in caplog.records), caplog.text
    assert fake_redis.get(key) is None, "the lock must be released when the scheduler exits"


def test_a_live_sibling_still_wins(fake_redis, monkeypatch):
    """The invariant the lock exists for: no second scheduler while one runs."""
    monkeypatch.setattr(redis_lock, "instance_identity", lambda: "schedulerhost:1")
    key = redis_lock.lock_key("scheduler")
    fake_redis.set(key, "differenthost:7", nx=True, ex=900)

    monkeypatch.setattr(scheduler_module, "build_scheduler", lambda: pytest.fail("must not build a second scheduler"))
    with pytest.raises(SystemExit) as exit_info:
        scheduler_module.main()
    assert "refusing to start a duplicate" in str(exit_info.value)
    assert fake_redis.get(key) == "differenthost:7", "another instance's lock must be left alone"


class _StubScheduler:
    """Stands in for BlockingScheduler: records that start() was reached."""

    def __init__(self, started: list[bool]) -> None:
        self.started = started

    def add_job(self, *args, **kwargs) -> None:  # noqa: D102 - no behaviour needed
        return None

    def start(self) -> None:
        self.started.append(True)
