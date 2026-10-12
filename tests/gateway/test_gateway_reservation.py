from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.api.services.gateway_wallet_service import (
    gateway_wallet,
    release_gateway_request_funds,
    reserve_gateway_request_funds,
    settle_gateway_request_funds,
)
from packages.database.models import (
    GatewayModel,
    GatewayPriceRevision,
    GatewayProvider,
    GatewayRequestReservation,
    GatewayWallet,
    GatewayWalletLedger,
)
from packages.gateway.contracts import GatewayProviderError


def _seed_catalog(db, provider_name: str = "reserve-test-provider"):
    provider = GatewayProvider(
        name=provider_name,
        display_name="Reservation test",
        base_url="https://official.example",
        health_status="healthy",
    )
    db.add(provider)
    db.flush()
    model = GatewayModel(
        public_id=f"{provider_name}-model",
        provider_id=provider.id,
        provider_model_id="official-test",
        display_name="Reservation test model",
        status="active",
    )
    db.add(model)
    db.flush()
    pricing = GatewayPriceRevision(
        model_id=model.id,
        status="active",
        # One USD per unit makes the arithmetic in these tests exact.
        official_prices_json={"input": {"usd": "1", "unit": "per_unit"}},
        final_prices_json={"input": {"usd": "1", "unit": "per_unit"}},
    )
    db.add(pricing)
    db.flush()
    model.active_pricing_id = pricing.id
    db.commit()
    return provider, model, pricing


def test_reserve_holds_are_atomic_and_release_is_idempotent(db, demo_user):
    wallet = gateway_wallet(db, demo_user.id)
    wallet.available_balance_usd = Decimal("10")
    db.commit()

    first = reserve_gateway_request_funds(
        db,
        user_id=demo_user.id,
        request_id="reserve-1",
        amount_usd=Decimal("6"),
    )
    assert first.status == "held"
    assert first.amount_usd == Decimal("6.00000000")
    assert db.get(GatewayWallet, wallet.id).reserved_usd == Decimal("6.00000000")

    # A second request cannot reserve money the first one has already claimed.
    with pytest.raises(GatewayProviderError) as exc:
        reserve_gateway_request_funds(
            db,
            user_id=demo_user.id,
            request_id="reserve-2",
            amount_usd=Decimal("6"),
        )
    assert exc.value.code == "GATEWAY_INSUFFICIENT_BALANCE"
    assert exc.value.status_code == 402

    # The same request id is idempotent, not a second hold.
    again = reserve_gateway_request_funds(
        db,
        user_id=demo_user.id,
        request_id="reserve-1",
        amount_usd=Decimal("6"),
    )
    assert again.id == first.id
    assert db.get(GatewayWallet, wallet.id).reserved_usd == Decimal("6.00000000")

    released = release_gateway_request_funds(db, request_id="reserve-1")
    assert released is not None and released.status == "released"
    assert db.get(GatewayWallet, wallet.id).reserved_usd == Decimal("0.00000000")
    # Releasing twice must not drive the hold negative.
    release_gateway_request_funds(db, request_id="reserve-1")
    assert db.get(GatewayWallet, wallet.id).reserved_usd == Decimal("0.00000000")


def test_settle_marks_the_reservation_without_double_charging(db, demo_user):
    wallet = gateway_wallet(db, demo_user.id)
    wallet.available_balance_usd = Decimal("5")
    db.commit()
    reserve_gateway_request_funds(db, user_id=demo_user.id, request_id="settle-1", amount_usd=Decimal("3"))

    settled = settle_gateway_request_funds(db, request_id="settle-1", amount_usd=Decimal("1.25"))
    assert settled is not None and settled.status == "released"
    refreshed = db.get(GatewayWallet, wallet.id)
    assert refreshed.reserved_usd == Decimal("0.00000000")
    # Settlement only releases the hold; the metered debit remains the single
    # owner of the balance change, so no ledger row appears here.
    assert db.query(GatewayWalletLedger).count() == 0


def test_unfunded_stream_is_rejected_before_any_provider_work(api_client, pro_user, db, monkeypatch):
    import apps.api.routers.gateway as gateway_router

    monkeypatch.setattr(gateway_router, "_gateway_enabled", lambda: None)
    wallet = gateway_wallet(db, pro_user.id)
    wallet.available_balance_usd = Decimal("0.00000001")
    db.commit()
    _seed_catalog(db)
    calls: list[str] = []

    def _forbidden_stream(*_args, **_kwargs):
        calls.append("stream_chat")
        raise AssertionError("the provider must not be called for an unfunded request")

    monkeypatch.setattr(gateway_router, "stream_chat", _forbidden_stream)
    from packages.gateway.security import create_api_key

    _key, raw_key = create_api_key(db, pro_user, name="Reservation test key")
    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={
            "model": "reserve-test-provider-model",
            "messages": [{"role": "user", "content": "ping"}],
            "stream": True,
            "max_tokens": 1000,
        },
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "GATEWAY_INSUFFICIENT_BALANCE"
    assert calls == []
    refreshed = db.get(GatewayWallet, wallet.id)
    assert refreshed.reserved_usd == Decimal("0.00000000")
    assert db.query(GatewayRequestReservation).count() == 0


def test_funded_request_holds_then_releases_after_settlement(api_client, pro_user, db, monkeypatch):
    import apps.api.routers.gateway as gateway_router
    from packages.database.models import GatewayRequestLog
    from packages.gateway.contracts import GatewayChatResult, GatewayUsage
    from packages.gateway.security import create_api_key
    from packages.gateway.service import GatewayRoute

    monkeypatch.setattr(gateway_router, "_gateway_enabled", lambda: None)
    wallet = gateway_wallet(db, pro_user.id)
    wallet.available_balance_usd = Decimal("5000")
    db.commit()
    provider, model, pricing = _seed_catalog(db)
    result = GatewayChatResult(content="pong", finish_reason="stop", usage=GatewayUsage(input_tokens=25, output_tokens=4))
    route = GatewayRoute(model=model, provider=provider, pricing=pricing, adapter=None)  # type: ignore[arg-type]
    monkeypatch.setattr(gateway_router, "execute_chat", lambda *_args, **_kwargs: (result, route))
    _key, raw_key = create_api_key(db, pro_user, name="Funded reservation key")

    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={
            "model": "reserve-test-provider-model",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1000,
        },
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "pong"
    log = db.query(GatewayRequestLog).one()
    reservations = db.query(GatewayRequestReservation).all()
    assert len(reservations) == 1
    db.refresh(reservations[0])
    assert reservations[0].request_id == log.request_id
    assert reservations[0].status == "released"
    refreshed = db.get(GatewayWallet, wallet.id)
    assert refreshed.reserved_usd == Decimal("0.00000000")
    # 25 input tokens at 1 USD per unit settle the real 25 USD charge, while the
    # 4142 USD worst-case hold (payload-derived input plus the 1000-token output
    # allowance, both at 1 USD per unit) is fully returned to the balance.
    assert refreshed.available_balance_usd == Decimal("858.00000000")


def test_openai_models_endpoint_is_untouched(api_client, pro_user, db, monkeypatch):
    import apps.api.routers.gateway as gateway_router
    from packages.gateway.security import create_api_key

    monkeypatch.setattr(gateway_router, "_gateway_enabled", lambda: None)
    _seed_catalog(db)
    _key, raw_key = create_api_key(db, pro_user, name="Model list key")
    response = api_client.get("/v1/models", headers={"Authorization": f"Bearer {raw_key}"})
    assert response.status_code == 200
    assert any(item["id"] == "reserve-test-provider-model" for item in response.json()["data"])
