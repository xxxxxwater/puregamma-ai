from __future__ import annotations

from decimal import Decimal

from apps.api.services.billing_service import process_stripe_event
from apps.api.services.gateway_wallet_service import create_gateway_topup_checkout, gateway_wallet, topup_amount_to_cents
from packages.database.models import GatewayApiKey, GatewayModel, GatewayPriceRevision, GatewayProvider, GatewayTopupIntent, GatewayWalletLedger
from packages.gateway.contracts import GatewayProviderError, GatewayUsage
from packages.gateway.security import create_api_key
from packages.gateway.service import GatewayRoute, assert_gateway_account_available, record_request
from tests.conftest import stripe_event


def _paid_checkout(intent: GatewayTopupIntent) -> dict:
    return {
        "id": intent.stripe_checkout_session_id,
        "customer": intent.stripe_customer_id,
        "payment_status": "paid",
        "amount_total": intent.amount_cents,
        "currency": intent.currency.lower(),
        "payment_intent": "pi_gateway_topup_test",
        "metadata": {
            "purpose": "gateway_topup",
            "gateway_topup_intent_id": intent.id,
            "user_id": intent.user_id,
            "amount_cents": str(intent.amount_cents),
            "currency": intent.currency,
        },
    }


def test_gateway_topup_uses_a_separate_wallet_and_is_idempotent(db, demo_user):
    original_credits = demo_user.credit_balance
    original_plan = demo_user.plan
    checkout = create_gateway_topup_checkout(db, demo_user, "25.50", locale="en")
    intent = db.get(GatewayTopupIntent, checkout["topup"]["id"])
    assert intent is not None
    assert intent.amount_cents == 2550
    assert intent.status == "checkout_created"

    event, raw = stripe_event("evt_gateway_topup_1", "checkout.session.completed", _paid_checkout(intent))
    result = process_stripe_event(db, event, raw)
    db.refresh(demo_user)
    wallet = gateway_wallet(db, demo_user.id)

    assert result["processed"] is True
    assert wallet.available_balance_usd == Decimal("25.50000000")
    assert demo_user.credit_balance == original_credits
    assert demo_user.plan == original_plan

    replay, replay_raw = stripe_event("evt_gateway_topup_2", "checkout.session.async_payment_succeeded", _paid_checkout(intent))
    process_stripe_event(db, replay, replay_raw)
    db.refresh(wallet)
    assert wallet.available_balance_usd == Decimal("25.50000000")
    assert db.query(GatewayWalletLedger).filter_by(entry_type="topup").count() == 1


def test_gateway_topup_amount_mismatch_is_held_for_manual_review(db, demo_user):
    checkout = create_gateway_topup_checkout(db, demo_user, "10.00", locale="zh")
    intent = db.get(GatewayTopupIntent, checkout["topup"]["id"])
    assert intent is not None
    payload = _paid_checkout(intent)
    payload["amount_total"] = 999
    event, raw = stripe_event("evt_gateway_topup_mismatch", "checkout.session.completed", payload)

    result = process_stripe_event(db, event, raw)
    db.refresh(intent)

    assert result["requires_manual_review"] is True
    assert intent.status == "requires_manual_review"
    assert db.query(GatewayWalletLedger).count() == 0


def test_gateway_topup_amount_requires_exact_cents_and_limits():
    assert topup_amount_to_cents("5") == 500
    assert topup_amount_to_cents("5.25") == 525
    for amount in ("4.99", "5.001", "10000.01", "not-a-number"):
        try:
            topup_amount_to_cents(amount)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected invalid top-up amount: {amount}")


def test_gateway_key_is_independent_from_puregamma_subscription(db, demo_user):
    assert demo_user.plan == "Free"
    _key, raw = create_api_key(db, demo_user, name="Gateway-only key")
    assert raw.startswith("sk-pg-")


def test_gateway_usage_debits_only_the_prepaid_wallet_and_never_overdrafts(db, demo_user):
    wallet = gateway_wallet(db, demo_user.id)
    wallet.available_balance_usd = Decimal("2.00")
    api_key = GatewayApiKey(
        user_id=demo_user.id,
        name="wallet test",
        key_hint="sk-pg-wallet-test",
        key_hash="not-used-by-this-test",
        last_four="test",
    )
    provider = GatewayProvider(name="wallet-test-provider", display_name="Wallet test", base_url="https://official.example", health_status="healthy")
    db.add_all((api_key, provider))
    db.flush()
    model = GatewayModel(public_id="wallet-test-model", provider_id=provider.id, provider_model_id="wallet-test", display_name="Wallet test", status="active")
    db.add(model)
    db.flush()
    pricing = GatewayPriceRevision(
        model_id=model.id,
        status="active",
        official_prices_json={"input": {"usd": "1", "unit": "per_unit"}},
        final_prices_json={"input": {"usd": "1", "unit": "per_unit"}},
    )
    db.add(pricing)
    db.flush()
    model.active_pricing_id = pricing.id
    db.commit()
    route = GatewayRoute(model=model, provider=provider, pricing=pricing, adapter=None)  # type: ignore[arg-type]

    assert_gateway_account_available(db, demo_user.id)
    record_request(
        db,
        request_id="wallet-debit-1",
        api_key=api_key,
        route=route,
        public_model=model.public_id,
        usage=GatewayUsage(input_tokens=1),
        status="success",
        http_status=200,
        latency_ms=1,
        ip_address="127.0.0.1",
    )
    db.refresh(wallet)
    assert wallet.available_balance_usd == Decimal("1.00000000")
    assert demo_user.credit_balance == 150

    try:
        record_request(
            db,
            request_id="wallet-debit-2",
            api_key=api_key,
            route=route,
            public_model=model.public_id,
            usage=GatewayUsage(input_tokens=2),
            status="success",
            http_status=200,
            latency_ms=1,
            ip_address="127.0.0.1",
        )
    except GatewayProviderError as exc:
        db.rollback()
        assert exc.code == "GATEWAY_INSUFFICIENT_BALANCE"
    else:
        raise AssertionError("wallet must not allow an overdraft")

    db.refresh(wallet)
    assert wallet.available_balance_usd == Decimal("1.00000000")
    assert db.query(GatewayWalletLedger).filter_by(entry_type="usage").count() == 1
