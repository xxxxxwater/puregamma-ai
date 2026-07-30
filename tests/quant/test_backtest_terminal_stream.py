from __future__ import annotations

import json

from apps.api.dependencies import create_access_token
from apps.api.routers import backtest_lab
from packages.backtest.logger import BacktestLogger
from packages.database.models import BacktestRun


def _auth_headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


class _FakePipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self.redis = redis

    def rpush(self, key: str, value: str):
        self.redis.values.setdefault(key, []).append(value)
        return self

    def ltrim(self, key: str, start: int, _end: int):
        self.redis.values[key] = self.redis.values.get(key, [])[start:]
        return self

    def expire(self, key: str, ttl: int):
        self.redis.expirations[key] = ttl
        return self

    def publish(self, channel: str, value: str):
        self.redis.published.append((channel, value))
        return self

    def execute(self):
        return []


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, list[str]] = {}
        self.counters: dict[str, int] = {}
        self.expirations: dict[str, int] = {}
        self.published: list[tuple[str, str]] = []

    def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def pipeline(self, *, transaction: bool):
        assert transaction is True
        return _FakePipeline(self)


def test_terminal_logger_persists_a_bounded_replayable_transcript():
    redis = _FakeRedis()
    log = BacktestLogger("run-terminal", redis, ttl_seconds=42, max_events=3)

    log.start(["BTC"], 100, "vectorbt", "binance")
    log.progress(50, 100, "BTC", 64_100.5, 102_350)
    log.error("bad\nmessage\x00")
    log.close()
    log.close()  # Closing twice must not duplicate the terminal event.

    assert len(redis.values[log.history_key]) == 3
    events = [json.loads(raw) for raw in redis.values[log.history_key]]
    assert [event["seq"] for event in events] == [2, 3, 4]
    assert events[0]["t"] == "progress"
    assert "██████████" in events[0]["line"]
    assert events[1]["line"] == "✗ bad message"
    assert events[-1]["t"] == "close"
    assert redis.expirations[log.history_key] == 42
    assert redis.expirations[log.sequence_key] == 42
    assert len(redis.published) == 4


class _ReplayPubSub:
    def subscribe(self, _channel: str) -> None:
        return None

    def unsubscribe(self, _channel: str) -> None:
        return None

    def close(self) -> None:
        return None


class _ReplayRedis:
    def __init__(self, events: list[dict]) -> None:
        self.events = events

    def ping(self) -> bool:
        return True

    def pubsub(self, *, ignore_subscribe_messages: bool):
        assert ignore_subscribe_messages is True
        return _ReplayPubSub()

    def lrange(self, _key: str, _start: int, _end: int) -> list[str]:
        return [json.dumps(event) for event in self.events]


def test_terminal_stream_replays_only_the_authenticated_users_run(api_client, db, max_user, user_factory, monkeypatch):
    run = BacktestRun(
        user_id=max_user.id,
        idempotency_key="terminal-stream-run",
        status="completed",
        engine="vectorbt",
        strategy_name="BTC trend",
        asset="BTC",
        params_json={},
        spec_json={},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    replay = _ReplayRedis(
        [
            {"t": "start", "seq": 1, "line": "▶ Starting vectorbt backtest"},
            {"t": "close", "seq": 2, "line": "── stream ended ──"},
        ]
    )
    monkeypatch.setattr(backtest_lab, "get_redis", lambda: replay)

    response = api_client.get(
        f"/backtest-lab/runs/{run.id}/stream",
        headers=_auth_headers(max_user),
    )

    assert response.status_code == 200
    assert "id: 1" in response.text
    assert "Starting vectorbt" in response.text
    assert "id: 2" in response.text

    other_user = user_factory("other-terminal-user@puregamma.ai", plan="Max", credit_balance=10_000)
    denied = api_client.get(
        f"/backtest-lab/runs/{run.id}/stream",
        headers=_auth_headers(other_user),
    )
    assert denied.status_code == 404
