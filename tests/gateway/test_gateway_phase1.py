from __future__ import annotations

import httpx

from apps.api.config import Settings
from packages.database.models import GatewayApiKey, GatewayModel, GatewayPriceRevision, GatewayProvider, GatewayRequestLog
from packages.gateway.contracts import GatewayChatResult, GatewayUsage
from packages.gateway.pricing import final_prices, usage_cost
from packages.gateway.providers.deepseek import DeepSeekGatewayProvider
from packages.gateway.security import create_api_key
from packages.gateway.service import GatewayRoute
from apps.api.services.gateway_wallet_service import gateway_wallet
from tests.conftest import auth_headers


def test_gateway_key_is_only_returned_once_and_hashed(api_client, pro_user, db):
    response = api_client.post("/gateway/keys", headers=auth_headers(pro_user), json={"name": "CI key"})
    assert response.status_code == 201
    raw_key = response.json()["key"]
    assert raw_key.startswith("sk-pg-")

    row = db.query(GatewayApiKey).one()
    assert row.key_hash != raw_key
    assert raw_key not in row.key_hash

    listed = api_client.get("/gateway/keys", headers=auth_headers(pro_user))
    assert listed.status_code == 200
    assert "key" not in listed.json()["keys"][0]
    assert listed.json()["keys"][0]["prefix"] == raw_key[:18]


def test_gateway_key_limit_is_ten(api_client, pro_user):
    for index in range(10):
        response = api_client.post("/gateway/keys", headers=auth_headers(pro_user), json={"name": f"key {index}"})
        assert response.status_code == 201
    response = api_client.post("/gateway/keys", headers=auth_headers(pro_user), json={"name": "eleventh"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "GATEWAY_API_KEY_LIMIT"


def test_gateway_admin_can_set_user_access_and_monthly_limit(api_client, pro_user, admin_user):
    response = api_client.get("/admin/gateway/accounts", headers=auth_headers(admin_user))
    assert response.status_code == 200
    account = next(row for row in response.json()["accounts"] if row["user_id"] == pro_user.id)
    assert account["account_status"] == "active"
    assert account["monthly_spend_limit_usd"] == "0"

    updated = api_client.patch(
        f"/admin/gateway/accounts/{pro_user.id}",
        headers=auth_headers(admin_user),
        json={"status": "suspended", "monthly_spend_limit_usd": "25.50"},
    )
    assert updated.status_code == 200
    payload = updated.json()["account"]
    assert payload["account_status"] == "suspended"
    assert payload["monthly_spend_limit_usd"] == "25.50000000"


def test_gateway_admin_account_guardrails_require_admin(api_client, normal_user, pro_user):
    response = api_client.get("/admin/gateway/accounts", headers=auth_headers(normal_user))
    assert response.status_code == 403

    response = api_client.patch(
        f"/admin/gateway/accounts/{pro_user.id}",
        headers=auth_headers(normal_user),
        json={"status": "suspended", "monthly_spend_limit_usd": 10},
    )
    assert response.status_code == 403


def test_pricing_applies_markup_to_every_supported_sku():
    official = {
        "input": {"usd": "1", "unit": "per_million_tokens"},
        "output": {"usd": "5", "unit": "per_million_tokens"},
        "cache": {"usd": "0.5", "unit": "per_million_tokens"},
        "upload": {"usd": "2", "unit": "per_unit"},
    }
    retail = final_prices(official, 3000)
    assert retail["input"]["usd"] == "1.30000000"
    assert retail["output"]["usd"] == "6.50000000"
    assert retail["cache"]["usd"] == "0.65000000"
    assert retail["upload"]["usd"] == "2.60000000"
    assert str(usage_cost(retail, GatewayUsage(input_tokens=1_000_000, output_tokens=1_000_000, upload_units=2))) == "13.00000000"


def test_provider_health_rejects_unauthorized_official_endpoint(monkeypatch):
    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url, **_kwargs):
            return httpx.Response(401, request=httpx.Request("GET", url))

    import packages.gateway.providers.openai_compatible as provider_module

    monkeypatch.setattr(provider_module.httpx, "Client", FakeClient)
    provider = DeepSeekGatewayProvider(
        Settings(
            gateway_deepseek_api_key="server-only-key",
            gateway_deepseek_base_url="https://official.example/v1",
        ),
        {"health_path": "models"},
    )

    assert provider.healthCheck() == {
        "healthy": False,
        "status": "unhealthy",
        "http_status": 401,
        "error": "HTTP 401",
    }


def test_openai_completion_shape_and_request_metering(api_client, pro_user, db, monkeypatch):
    # API-key middleware normally checks the feature gate; test the protocol
    # independently from deployment configuration.
    import apps.api.routers.gateway as gateway_router

    monkeypatch.setattr(gateway_router, "_gateway_enabled", lambda: None)
    wallet = gateway_wallet(db, pro_user.id)
    wallet.available_balance_usd = 1
    db.commit()
    key, raw_key = create_api_key(db, pro_user, name="Gateway test")
    provider = GatewayProvider(name="test-provider", display_name="Test", base_url="https://official.example")
    db.add(provider)
    db.flush()
    model = GatewayModel(public_id="test-model", provider_id=provider.id, provider_model_id="official-test", display_name="Test model", status="active")
    db.add(model)
    db.flush()
    price = GatewayPriceRevision(model_id=model.id, status="active", official_prices_json={"input": {"usd": "1"}}, final_prices_json={"input": {"usd": "1.3"}})
    db.add(price)
    db.flush()
    model.active_pricing_id = price.id
    db.commit()
    route = GatewayRoute(model=model, provider=provider, pricing=price, adapter=None)  # type: ignore[arg-type]
    result = GatewayChatResult(content="pong", finish_reason="stop", usage=GatewayUsage(input_tokens=25, output_tokens=4))
    monkeypatch.setattr(gateway_router, "execute_chat", lambda *_args, **_kwargs: (result, route))

    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "test-model", "messages": [{"role": "user", "content": "ping"}], "response_format": {"type": "json_object"}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["choices"][0]["message"]["content"] == "pong"
    assert payload["usage"]["prompt_tokens"] == 25
    log = db.query(GatewayRequestLog).one()
    assert log.api_key_id == key.id
    assert log.input_tokens == 25
    assert log.output_tokens == 4
