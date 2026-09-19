"""Offline integration tests: never use a real provider credential or paid API."""
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from apps.api.config import Settings
from apps.api.services.gateway_wallet_service import gateway_wallet
from packages.database.models import GatewayModel, GatewayPriceRevision, GatewayProvider, GatewayRequestLog
from packages.gateway.contracts import GatewayCapabilityUnavailable, GatewayProviderError, GatewayUsage
from packages.gateway.pricing import final_prices, usage_cost
from packages.gateway.providers.typesafe import TypeSafeJevProvider
from packages.gateway.security import create_api_key
from packages.gateway.service import GatewayRoute


QUESTION = {"urgent": {"type": "noul", "instructions": "Is this an urgent request?"}}
ANSWER = {"model": "jev-1.13.0", "answers": {"urgent": {"type": "noul", "noul": 0.9}}, "usage": {"input_tokens": 1000, "output_tokens": 15}}


def test_jev_official_pricing_is_decimal_and_output_is_free():
    official = {"input": {"usd": "0.042", "unit": "per_million_tokens"}, "output": {"usd": "0", "unit": "per_million_tokens"}}
    retail = final_prices(official, 3000)
    assert retail["input"]["usd"] == "0.05460000"
    assert retail["output"]["usd"] == "0E-8" or Decimal(retail["output"]["usd"]) == Decimal("0")
    assert usage_cost(retail, GatewayUsage(input_tokens=1_000_000, output_tokens=999_999)) == Decimal("0.05460000")
    assert usage_cost(retail, GatewayUsage(input_tokens=1000, output_tokens=15)) == Decimal("0.00005460")


def test_jev_posts_native_request_once_and_never_passes_a_chat_payload(monkeypatch):
    monkeypatch.setenv("GATEWAY_TYPESAFE_API_KEY", "offline-test-token")
    import packages.gateway.providers.typesafe as module
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs.get("follow_redirects") is False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(200, json=ANSWER, request=httpx.Request("POST", url))

    monkeypatch.setattr(module.httpx, "Client", FakeClient)
    provider = TypeSafeJevProvider(Settings())
    response, usage = provider.evaluate("jev-1.13.0", state={"message": "Please help now"}, questions=QUESTION)
    assert response["answers"]["urgent"]["noul"] == 0.9
    assert usage.input_tokens == 1000 and usage.output_tokens == 15
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "https://api.typesafe.ai/v1/systemone"
    assert kwargs["json"] == {"model": "jev-1.13.0", "state": {"message": "Please help now"}, "questions": QUESTION}
    assert "messages" not in kwargs["json"]
    with pytest.raises(GatewayCapabilityUnavailable):
        provider.chat("jev-1.13.0", {"messages": []})
    assert len(calls) == 1


def test_jev_missing_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("GATEWAY_TYPESAFE_API_KEY", raising=False)
    provider = TypeSafeJevProvider(Settings())
    assert provider.healthCheck()["healthy"] is False
    with pytest.raises(GatewayProviderError) as exc:
        provider.evaluate("jev-1.13.0", state="hello", questions=QUESTION)
    assert exc.value.code == "GATEWAY_PROVIDER_UNCONFIGURED"


def test_jev_missing_usage_is_not_silently_free(monkeypatch):
    monkeypatch.setenv("GATEWAY_TYPESAFE_API_KEY", "offline-test-token")
    import packages.gateway.providers.typesafe as module

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, **kwargs):
            return httpx.Response(200, json={"model": "jev-1.13.0", "answers": ANSWER["answers"]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(module.httpx, "Client", FakeClient)
    provider = TypeSafeJevProvider(Settings())
    with pytest.raises(GatewayProviderError) as exc:
        provider.evaluate("jev-1.13.0", state="hello", questions=QUESTION)
    assert exc.value.code == "GATEWAY_JEV_INVALID_RESPONSE"


def test_jev_systemone_endpoint_reuses_key_wallet_and_request_ledger(api_client, pro_user, db, monkeypatch):
    import apps.api.routers.gateway as legacy_router
    import apps.api.routers.jev_gateway as jev_router

    monkeypatch.setattr(legacy_router, "_gateway_enabled", lambda: None)
    # Dependencies capture the original callable: alter the installed FastAPI
    # dependency instead of assuming the imported name can be monkeypatched.
    from apps.api.main import app
    app.dependency_overrides[jev_router._gateway_key] = lambda: api_key
    wallet = gateway_wallet(db, pro_user.id)
    wallet.available_balance_usd = Decimal("1")
    db.commit()
    api_key, raw_key = create_api_key(db, pro_user, name="jev-test")
    provider = GatewayProvider(name="typesafe", display_name="TypeSafe", base_url="https://api.typesafe.ai", enabled=True)
    db.add(provider)
    db.flush()
    model = GatewayModel(public_id="jev-1.13.0", provider_id=provider.id, provider_model_id="jev-1.13.0", display_name="Jev", status="active", capabilities_json={"chat": False, "system_one": True})
    db.add(model)
    db.flush()
    official = {"input": {"usd": "0.042", "unit": "per_million_tokens"}, "output": {"usd": "0", "unit": "per_million_tokens"}}
    price = GatewayPriceRevision(model_id=model.id, status="active", official_prices_json=official, final_prices_json=final_prices(official, 3000))
    db.add(price)
    db.flush()
    model.active_pricing_id = price.id
    db.commit()

    class Adapter(TypeSafeJevProvider):
        def evaluate(self, model, *, state, questions):
            assert model == "jev-1.13.0" and state == "Please help now" and questions == QUESTION
            return ANSWER, GatewayUsage(input_tokens=1000, output_tokens=15)

    route = GatewayRoute(model=model, provider=provider, pricing=price, adapter=Adapter(Settings()))
    monkeypatch.setattr(jev_router, "_route_for_model", lambda *_args: route)
    response = api_client.post("/v1/systemone", headers={"Authorization": f"Bearer {raw_key}"}, json={"model": "jev-1.13.0", "state": "Please help now", "questions": QUESTION})
    assert response.status_code == 200, response.text
    assert response.json()["answers"]["urgent"]["noul"] == 0.9
    assert response.json()["billing"]["amount_usd"] == "0.00005460"
    log = db.query(GatewayRequestLog).filter_by(public_model="jev-1.13.0").one()
    assert log.api_key_id == api_key.id and log.input_tokens == 1000 and log.output_tokens == 15
    assert Decimal(str(log.retail_cost_usd)) == Decimal("0.00005460")
    db.refresh(wallet)
    assert Decimal(str(wallet.available_balance_usd)) < Decimal("1")
    app.dependency_overrides.pop(jev_router._gateway_key, None)


def test_jev_rejects_chat_shaped_request_and_invalid_question(api_client):
    response = api_client.post("/v1/systemone", json={"model": "jev-1.13.0", "messages": [{"role": "user", "content": "Hello"}]})
    assert response.status_code in {401, 422}
    from apps.api.routers.jev_gateway import SystemOneRequest
    with pytest.raises(ValueError):
        SystemOneRequest(model="jev-1.13.0", state="x", questions={"q": {"type": "choice", "instructions": "Which?", "criteria": {"only": None}}})
