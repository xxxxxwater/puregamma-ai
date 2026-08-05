from __future__ import annotations

from datetime import datetime, timedelta, timezone

from packages.database.models import GatewayApiKey, GatewayRequestLog
from packages.gateway.security import create_api_key
from tests.conftest import auth_headers


def _log(db, user, key, model, created_at, *, status="success", input_tokens=0, output_tokens=0, cache_tokens=0, latency_ms=100, cost="0"):
    row = GatewayRequestLog(
        request_id=f"req-{created_at.timestamp()}-{model}-{user.id[:6]}",
        user_id=user.id,
        api_key_id=key.id,
        public_model=model,
        status=status,
        http_status=200 if status == "success" else 500,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_tokens=cache_tokens,
        reasoning_tokens=0,
        provider_cost_usd=cost,
        retail_cost_usd=cost,
        created_at=created_at,
    )
    db.add(row)
    return row


def test_usage_returns_zero_filled_buckets(api_client, pro_user, db):
    key, _ = create_api_key(db, pro_user, name="usage key")
    start = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    _log(db, pro_user, key, "deepseek-v4-flash", start, input_tokens=100, output_tokens=50, cost="0.01")
    db.commit()

    response = api_client.get(
        "/gateway/usage",
        headers=auth_headers(pro_user),
        params={"start": "2026-07-01", "end": "2026-07-05", "granularity": "day"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["buckets"]) == 5
    assert payload["buckets"][0]["requests"] == 1
    assert payload["buckets"][0]["input_tokens"] == 100
    assert payload["buckets"][1]["requests"] == 0
    assert payload["buckets"][1]["input_tokens"] == 0
    assert payload["buckets"][2]["requests"] == 0
    assert payload["buckets"][3]["requests"] == 0
    assert payload["buckets"][4]["requests"] == 0
    assert payload["totals"]["requests"] == 1
    assert payload["totals"]["input_tokens"] == 100


def test_usage_hour_granularity_and_totals(api_client, pro_user, db):
    key, _ = create_api_key(db, pro_user, name="usage hour")
    base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
    _log(db, pro_user, key, "deepseek-v4-flash", base + timedelta(minutes=10), input_tokens=10, output_tokens=2, latency_ms=120, cost="0.001")
    _log(db, pro_user, key, "deepseek-v4-pro", base + timedelta(minutes=40), input_tokens=20, output_tokens=3, latency_ms=240, cost="0.002")
    _log(db, pro_user, key, "deepseek-v4-pro", base + timedelta(hours=1, minutes=5), input_tokens=30, output_tokens=4, latency_ms=60, cost="0.003")
    db.commit()

    response = api_client.get(
        "/gateway/usage",
        headers=auth_headers(pro_user),
        params={"start": "2026-07-01T00:00:00+00:00", "end": "2026-07-01T03:00:00+00:00", "granularity": "hour"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["buckets"]) == 4
    assert payload["buckets"][0]["requests"] == 2
    assert payload["buckets"][0]["success"] == 2
    assert payload["buckets"][0]["input_tokens"] == 30
    assert payload["buckets"][1]["requests"] == 1
    assert payload["buckets"][2]["requests"] == 0
    assert payload["buckets"][3]["requests"] == 0
    assert payload["totals"]["requests"] == 3
    assert payload["totals"]["input_tokens"] == 60
    assert payload["totals"]["output_tokens"] == 9


def test_usage_breaks_down_by_model_and_key(api_client, pro_user, db):
    key_a, _ = create_api_key(db, pro_user, name="key a")
    key_b, _ = create_api_key(db, pro_user, name="key b")
    base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
    _log(db, pro_user, key_a, "deepseek-v4-flash", base, input_tokens=100, cost="0.05")
    _log(db, pro_user, key_a, "deepseek-v4-pro", base + timedelta(minutes=1), input_tokens=200, cost="0.20")
    _log(db, pro_user, key_b, "deepseek-v4-flash", base + timedelta(minutes=2), input_tokens=300, cost="0.10")
    db.commit()

    response = api_client.get(
        "/gateway/usage",
        headers=auth_headers(pro_user),
        params={"start": "2026-07-01", "end": "2026-07-02"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert [row["model"] for row in payload["by_model"]] == ["deepseek-v4-pro", "deepseek-v4-flash"]
    assert payload["by_model"][0]["requests"] == 1
    assert payload["by_model"][1]["requests"] == 2
    assert payload["by_model"][1]["input_tokens"] == 400

    by_key = {row["name"]: row for row in payload["by_key"]}
    assert by_key["key a"]["requests"] == 2
    assert by_key["key b"]["requests"] == 1
    assert by_key["key a"]["cost_usd"] == "0.25000000"


def test_usage_counts_errors_and_latency(api_client, pro_user, db):
    key, _ = create_api_key(db, pro_user, name="usage errors")
    base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
    _log(db, pro_user, key, "deepseek-v4-flash", base, status="success", latency_ms=100)
    _log(db, pro_user, key, "deepseek-v4-flash", base + timedelta(minutes=1), status="error", latency_ms=500)
    _log(db, pro_user, key, "deepseek-v4-flash", base + timedelta(minutes=2), status="error", latency_ms=700)
    db.commit()

    response = api_client.get(
        "/gateway/usage",
        headers=auth_headers(pro_user),
        params={"start": "2026-07-01", "end": "2026-07-02"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["totals"]["requests"] == 3
    assert payload["totals"]["success"] == 1
    assert payload["totals"]["errors"] == 2
    assert payload["totals"]["max_latency_ms"] == 700
    assert payload["buckets"][0]["errors"] == 2


def test_usage_filters_by_model_and_key(api_client, pro_user, db):
    key_a, _ = create_api_key(db, pro_user, name="filter a")
    key_b, _ = create_api_key(db, pro_user, name="filter b")
    base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
    _log(db, pro_user, key_a, "deepseek-v4-flash", base, input_tokens=10)
    _log(db, pro_user, key_a, "deepseek-v4-pro", base + timedelta(minutes=1), input_tokens=20)
    _log(db, pro_user, key_b, "deepseek-v4-flash", base + timedelta(minutes=2), input_tokens=30)
    db.commit()

    response = api_client.get(
        "/gateway/usage",
        headers=auth_headers(pro_user),
        params={"start": "2026-07-01", "end": "2026-07-02", "model": "deepseek-v4-flash"},
    )
    assert response.status_code == 200
    assert response.json()["totals"]["requests"] == 2

    response = api_client.get(
        "/gateway/usage",
        headers=auth_headers(pro_user),
        params={"start": "2026-07-01", "end": "2026-07-02", "api_key_id": key_a.id},
    )
    assert response.status_code == 200
    assert response.json()["totals"]["requests"] == 2


def test_usage_is_scoped_to_own_user(api_client, pro_user, normal_user, db):
    key, _ = create_api_key(db, pro_user, name="scoped")
    base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
    _log(db, pro_user, key, "deepseek-v4-flash", base, input_tokens=10)
    db.commit()

    response = api_client.get(
        "/gateway/usage",
        headers=auth_headers(normal_user),
        params={"start": "2026-07-01", "end": "2026-07-02"},
    )
    assert response.status_code == 200
    assert response.json()["totals"]["requests"] == 0


def test_usage_rejects_invalid_params(api_client, pro_user):
    response = api_client.get("/gateway/usage", headers=auth_headers(pro_user), params={"start": "not-a-date"})
    assert response.status_code == 422

    response = api_client.get(
        "/gateway/usage",
        headers=auth_headers(pro_user),
        params={"start": "2026-01-01", "end": "2026-07-01"},
    )
    assert response.status_code == 422

    response = api_client.get(
        "/gateway/usage",
        headers=auth_headers(pro_user),
        params={"start": "2026-07-05", "end": "2026-07-01"},
    )
    assert response.status_code == 422

    response = api_client.get("/gateway/usage", headers=auth_headers(pro_user), params={"granularity": "week"})
    assert response.status_code == 422
