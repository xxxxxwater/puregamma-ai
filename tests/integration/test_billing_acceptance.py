"""P0-11 acceptance contract tests: Stripe/OAuth/Credits vertical slice.

All Stripe traffic is contract-level: webhook payloads are HMAC-signed exactly
the way Stripe signs them and verified by the real ``stripe`` SDK, while the
outbound Stripe API calls are monkeypatched. No live Stripe calls, no secrets.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import time
from dataclasses import replace
from datetime import datetime, timezone

import pytest
import stripe

from apps.api.config import Settings, validate_production_settings
from apps.api.services.credit_service import quote_task, refund_task, reserve_task, settle_task
from apps.api.services.entitlement_service import get_user_entitlement
from packages.billing.entitlements import can_run_action, entitlement_for_plan
from packages.database.models import (
    BillingCheckoutIntent,
    CreditLedger,
    CreditRefundEvent,
    CreditReservationRecord,
    CreditSettlementRecord,
    StripeWebhookEvent,
    Subscription,
)
from tests.conftest import auth_headers
from tests.security.test_production_configuration import valid_production_settings


WEBHOOK_SECRET = "whsec_acceptance_contract"
PRICE_BY_PLAN = {"Pro": "price_acceptance_pro", "Max": "price_acceptance_max", "Enterprise": "price_acceptance_enterprise"}
PERIOD_START_TS = 1_800_000_000
PERIOD_END_TS = 1_800_259_200


def _stripe_mode_settings(**overrides) -> Settings:
    base = dict(
        billing_mode="stripe",
        stripe_secret_key="sk_test_acceptance",
        stripe_webhook_secret=WEBHOOK_SECRET,
        stripe_webhook_tolerance_seconds=300,
        stripe_price_pro=PRICE_BY_PLAN["Pro"],
        stripe_price_max=PRICE_BY_PLAN["Max"],
        stripe_price_enterprise=PRICE_BY_PLAN["Enterprise"],
        stripe_success_url="https://app.puregamma.ai/billing/success",
        stripe_cancel_url="https://app.puregamma.ai/billing/cancel",
        openai_luna_enabled=True,
        openai_api_key="sk-luna-acceptance",
        openai_luna_model="gpt-5.6-luna",
        openai_luna_allowed_plans=("Max", "Enterprise"),
    )
    base.update(overrides)
    return Settings(**base)


SETTINGS_MODULES = (
    "apps.api.routers.stripe_webhook",
    "apps.api.routers.billing",
    "apps.api.services.billing_service",
    "apps.api.services.stripe_service",
    "apps.api.services.entitlement_service",
    "apps.api.services.credit_service",
    "packages.billing.stripe",
)


@pytest.fixture()
def stripe_mode(monkeypatch):
    """BILLING_MODE=stripe with the outbound Stripe API monkeypatched."""
    settings = _stripe_mode_settings()
    for module_name in SETTINGS_MODULES:
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        stripe.Customer,
        "create",
        lambda **params: {"id": f"cus_acceptance_{params['metadata']['user_id'][:8]}"},
    )
    monkeypatch.setattr(
        stripe.checkout.Session,
        "create",
        lambda **params: {
            "id": f"cs_acceptance_{params['line_items'][0]['price']}",
            "url": "https://checkout.stripe.com/pay/cs_acceptance",
        },
    )
    monkeypatch.setattr(
        stripe.Subscription,
        "retrieve",
        lambda subscription_id, **params: {"id": subscription_id, "status": "active"},
    )
    monkeypatch.setattr(
        stripe.Subscription,
        "modify",
        lambda subscription_id, **params: {
            "id": subscription_id,
            "cancel_at_period_end": params.get("cancel_at_period_end", False),
            "status": "active",
            "current_period_start": PERIOD_START_TS,
            "current_period_end": PERIOD_END_TS,
        },
    )
    return settings


def _sign(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    timestamp = int(time.time())
    signature = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def _post_signed_event(api_client, event_id: str, event_type: str, obj: dict):
    payload = json.dumps(
        {"id": event_id, "object": "event", "type": event_type, "data": {"object": obj}},
        separators=(",", ":"),
    ).encode()
    return api_client.post("/stripe/webhook", content=payload, headers={"Stripe-Signature": _sign(payload)})


def _checkout_and_activate(api_client, db, user, plan: str, *, event_id: str, session_id: str, subscription_id: str, customer_id: str) -> BillingCheckoutIntent:
    checkout = api_client.post("/billing/create-checkout-session", json={"plan_name": plan}, headers=auth_headers(user))
    assert checkout.status_code == 200, checkout.text
    intent = db.query(BillingCheckoutIntent).filter_by(id=checkout.json()["checkout_intent_id"]).one()
    assert intent.status == "created"
    response = _post_signed_event(
        api_client,
        event_id,
        "checkout.session.completed",
        {
            "id": session_id,
            "customer": customer_id,
            "subscription": subscription_id,
            "payment_status": "paid",
            "client_reference_id": intent.public_reference,
            "metadata": {"user_id": user.id, "plan_name": plan},
            "line_items": {"data": [{"price": {"id": PRICE_BY_PLAN[plan]}}]},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["processed"] is True
    assert response.json()["duplicate"] is False
    return intent


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 1/2/4. Checkout -> signed webhook -> subscription active -> entitlements/credits
# ---------------------------------------------------------------------------


def test_checkout_signed_webhook_activates_subscription_entitlements_and_credits(api_client, db, demo_user, stripe_mode):
    intent = _checkout_and_activate(
        api_client, db, demo_user, "Pro",
        event_id="evt_acc_checkout_pro", session_id="cs_acc_pro", subscription_id="sub_acc_pro", customer_id="cus_acc_pro",
    )
    db.refresh(demo_user)
    db.refresh(intent)

    assert demo_user.plan == "Pro"
    assert demo_user.stripe_customer_id == "cus_acc_pro"
    assert demo_user.credit_balance == 150 + 3000

    # Checkout Intent reaches status completed.
    assert intent.status == "completed"
    assert intent.completed_at is not None
    assert intent.stripe_checkout_session_id == "cs_acc_pro"
    assert intent.stripe_customer_id == "cus_acc_pro"

    webhook_row = db.query(StripeWebhookEvent).filter_by(stripe_event_id="evt_acc_checkout_pro").one()
    assert webhook_row.processed is True
    assert webhook_row.processed_at is not None
    assert webhook_row.event_type == "checkout.session.completed"

    subscription = db.query(Subscription).filter_by(user_id=demo_user.id).one()
    assert subscription.stripe_subscription_id == "sub_acc_pro"
    assert subscription.status == "active"
    assert subscription.plan_name == "Pro"

    contract = api_client.get("/billing/subscription", headers=auth_headers(demo_user))
    assert contract.status_code == 200
    body = contract.json()
    assert body["plan"] == "Pro"
    assert body["subscribed_plan"] == "Pro"
    assert body["effective_plan"] == "Pro"
    assert body["subscription_status"] == "active"
    assert body["cancel_at_period_end"] is False
    assert body["credit_balance"] == 3150
    assert body["billing_mode"] == "stripe"

    credits = api_client.get("/billing/credits", headers=auth_headers(demo_user))
    assert credits.status_code == 200
    assert credits.json()["credit_balance"] == 3150

    # Entitlements sync immediately on activation: plan, credits, model + skill gates.
    entitlement = get_user_entitlement(db, demo_user.id)
    assert entitlement["plan"] == "Pro"
    assert entitlement["effective_plan"] == "Pro"
    assert entitlement["monthly_credits"] == 3000
    assert entitlement["notification_channels"] == ["telegram", "email", "push"]
    assert entitlement["high_cost_tasks"] is True
    assert "options" in entitlement["allowed_data_sources"]
    assert entitlement["restricted_reason"] is None


def test_webhook_rejects_forged_signature_and_processes_nothing(api_client, db, demo_user, stripe_mode):
    payload = json.dumps(
        {
            "id": "evt_acc_forged",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_forged", "subscription": "sub_forged", "metadata": {"user_id": demo_user.id, "plan_name": "Max"}}},
        },
        separators=(",", ":"),
    ).encode()
    forged = api_client.post(
        "/stripe/webhook",
        content=payload,
        headers={"Stripe-Signature": _sign(payload, secret="whsec_forged_secret")},
    )
    db.refresh(demo_user)

    assert forged.status_code == 400
    assert "Invalid Stripe signature" in forged.json()["detail"]
    assert demo_user.plan == "Free"
    assert demo_user.credit_balance == 150
    assert db.query(StripeWebhookEvent).filter_by(stripe_event_id="evt_acc_forged").count() == 0


# ---------------------------------------------------------------------------
# 3. Webhook idempotency
# ---------------------------------------------------------------------------


def test_duplicate_signed_webhook_delivery_is_processed_once(api_client, db, demo_user, stripe_mode):
    _checkout_and_activate(
        api_client, db, demo_user, "Pro",
        event_id="evt_acc_dup", session_id="cs_acc_dup", subscription_id="sub_acc_dup", customer_id="cus_acc_dup",
    )
    db.refresh(demo_user)
    balance_after_first = demo_user.credit_balance
    assert balance_after_first == 3150

    intent = db.query(BillingCheckoutIntent).filter_by(stripe_checkout_session_id="cs_acc_dup").one()
    duplicate = _post_signed_event(
        api_client,
        "evt_acc_dup",
        "checkout.session.completed",
        {
            "id": "cs_acc_dup",
            "customer": "cus_acc_dup",
            "subscription": "sub_acc_dup",
            "payment_status": "paid",
            "client_reference_id": intent.public_reference,
            "metadata": {"user_id": demo_user.id, "plan_name": "Pro"},
            "line_items": {"data": [{"price": {"id": PRICE_BY_PLAN["Pro"]}}]},
        },
    )
    db.refresh(demo_user)
    db.refresh(intent)

    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["processed"] is False
    assert demo_user.credit_balance == balance_after_first
    assert db.query(StripeWebhookEvent).filter_by(stripe_event_id="evt_acc_dup").count() == 1
    row = db.query(StripeWebhookEvent).filter_by(stripe_event_id="evt_acc_dup").one()
    assert row.processed is True
    grants = db.query(CreditLedger).filter_by(user_id=demo_user.id, action="monthly_credit_grant").all()
    assert len(grants) == 1
    assert intent.status == "completed"


# ---------------------------------------------------------------------------
# 1/5. Renewal: period extends + credits grant idempotent
# ---------------------------------------------------------------------------


def test_renewal_extends_period_and_grants_credits_idempotently(api_client, db, demo_user, stripe_mode):
    _checkout_and_activate(
        api_client, db, demo_user, "Pro",
        event_id="evt_acc_renew_checkout", session_id="cs_acc_renew", subscription_id="sub_acc_renew", customer_id="cus_acc_renew",
    )

    updated = _post_signed_event(
        api_client,
        "evt_acc_renew_sub_updated",
        "customer.subscription.updated",
        {
            "id": "sub_acc_renew",
            "customer": "cus_acc_renew",
            "status": "active",
            "cancel_at_period_end": False,
            "current_period_start": PERIOD_START_TS,
            "current_period_end": PERIOD_END_TS,
            "items": {"data": [{"price": {"id": PRICE_BY_PLAN["Pro"]}}]},
        },
    )
    assert updated.json()["processed"] is True
    subscription = db.query(Subscription).filter_by(user_id=demo_user.id).one()
    expected_end = datetime.fromtimestamp(PERIOD_END_TS, tz=timezone.utc)
    assert subscription.current_period_end is not None
    assert _as_utc(subscription.current_period_end) == expected_end
    assert subscription.status == "active"

    renewal = _post_signed_event(
        api_client,
        "evt_acc_renew_invoice",
        "invoice.paid",
        {"id": "in_acc_renewal", "customer": "cus_acc_renew", "subscription": "sub_acc_renew", "billing_reason": "subscription_cycle"},
    )
    db.refresh(demo_user)
    assert renewal.json()["processed"] is True
    # Pro carryover cap 6000: min(3000, 6000 - 3150) = 2850 granted.
    assert demo_user.credit_balance == 6000
    grant = (
        db.query(CreditLedger)
        .filter(CreditLedger.action == "monthly_credit_grant", CreditLedger.metadata_json["invoice_id"].as_string() == "in_acc_renewal")
        .one()
    )
    assert grant.metadata_json["granted_credits"] == 2850
    assert grant.metadata_json["configured_grant"] == 3000

    replayed = _post_signed_event(
        api_client,
        "evt_acc_renew_invoice",
        "invoice.paid",
        {"id": "in_acc_renewal", "customer": "cus_acc_renew", "subscription": "sub_acc_renew", "billing_reason": "subscription_cycle"},
    )
    db.refresh(demo_user)
    assert replayed.json()["duplicate"] is True
    assert demo_user.credit_balance == 6000

    contract = api_client.get("/billing/subscription", headers=auth_headers(demo_user)).json()
    assert contract["subscription_status"] == "active"
    assert contract["current_period_end"] is not None
    assert contract["current_period_end"].startswith(expected_end.date().isoformat())


# ---------------------------------------------------------------------------
# 5. Cancel-at-period-end keeps plan until period end; delete revokes (Luna off)
# ---------------------------------------------------------------------------


def test_cancel_at_period_end_keeps_plan_then_delete_revokes_entitlements(api_client, db, demo_user, stripe_mode):
    _checkout_and_activate(
        api_client, db, demo_user, "Max",
        event_id="evt_acc_cancel_checkout", session_id="cs_acc_cancel", subscription_id="sub_acc_cancel", customer_id="cus_acc_cancel",
    )
    headers = auth_headers(demo_user)
    luna_quote = {"task_type": "luna_research", "requested_model": "gpt-5.6-luna"}
    assert api_client.post("/billing/quote", json=luna_quote, headers=headers).status_code == 200

    canceled = api_client.post("/billing/cancel-subscription", headers=headers)
    assert canceled.status_code == 200
    assert canceled.json()["cancel_at_period_end"] is True

    updated = _post_signed_event(
        api_client,
        "evt_acc_cancel_updated",
        "customer.subscription.updated",
        {
            "id": "sub_acc_cancel",
            "customer": "cus_acc_cancel",
            "status": "active",
            "cancel_at_period_end": True,
            "current_period_start": PERIOD_START_TS,
            "current_period_end": PERIOD_END_TS,
            "items": {"data": [{"price": {"id": PRICE_BY_PLAN["Max"]}}]},
        },
    )
    db.refresh(demo_user)
    assert updated.json()["processed"] is True

    # Plan + entitlements remain until period end.
    assert demo_user.plan == "Max"
    subscription = db.query(Subscription).filter_by(user_id=demo_user.id).one()
    assert subscription.status == "active"
    assert subscription.cancel_at_period_end is True
    entitlement = get_user_entitlement(db, demo_user.id)
    assert entitlement["effective_plan"] == "Max"
    assert entitlement["high_cost_tasks"] is True
    assert entitlement["imessage"] is True
    contract = api_client.get("/billing/subscription", headers=headers).json()
    assert contract["subscription_status"] == "active"
    assert contract["cancel_at_period_end"] is True
    assert contract["cancel_at"] is not None
    assert api_client.post("/billing/quote", json=luna_quote, headers=headers).status_code == 200

    deleted = _post_signed_event(
        api_client,
        "evt_acc_cancel_deleted",
        "customer.subscription.deleted",
        {"id": "sub_acc_cancel", "customer": "cus_acc_cancel", "metadata": {"user_id": demo_user.id, "plan_name": "Max"}},
    )
    db.refresh(demo_user)
    assert deleted.json()["processed"] is True

    assert demo_user.plan == "Free"
    contract = api_client.get("/billing/subscription", headers=headers).json()
    assert contract["subscription_status"] == "deleted"
    assert contract["effective_plan"] == "Free"
    entitlement = get_user_entitlement(db, demo_user.id)
    assert entitlement["plan"] == "Free"
    assert entitlement["monthly_credits"] == 150
    assert entitlement["notification_channels"] == ["email", "push"]
    assert entitlement["high_cost_tasks"] is False
    assert entitlement["imessage"] is False
    assert entitlement["restricted_reason"] == "subscription_restricted"

    # Luna is gated off immediately after the subscription is deleted.
    denied = api_client.post("/billing/quote", json=luna_quote, headers=headers)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "AGENT_MODEL_PLAN_REQUIRED"


# ---------------------------------------------------------------------------
# 5. invoice.payment_failed -> past_due surfaced in /billing/subscription
# ---------------------------------------------------------------------------


def test_invoice_payment_failed_surfaces_past_due_in_subscription_contract(api_client, db, demo_user, stripe_mode):
    _checkout_and_activate(
        api_client, db, demo_user, "Pro",
        event_id="evt_acc_failed_checkout", session_id="cs_acc_failed", subscription_id="sub_acc_failed", customer_id="cus_acc_failed",
    )

    failed = _post_signed_event(
        api_client,
        "evt_acc_invoice_failed",
        "invoice.payment_failed",
        {"id": "in_acc_failed", "customer": "cus_acc_failed", "subscription": "sub_acc_failed"},
    )
    assert failed.json()["processed"] is True

    contract = api_client.get("/billing/subscription", headers=auth_headers(demo_user)).json()
    assert contract["subscription_status"] == "past_due"
    assert contract["plan"] == "Pro"
    assert contract["subscribed_plan"] == "Pro"
    assert contract["effective_plan"] == "Free"
    assert contract["entitlement"]["restricted_reason"] == "payment_failed"
    assert contract["entitlement"]["high_cost_tasks"] is False
    assert contract["entitlement"]["notification_channels"] == ["email", "push"]


# ---------------------------------------------------------------------------
# 4. Luna plan gating via openai_luna_allowed_plans
# ---------------------------------------------------------------------------


def test_luna_model_gating_follows_allowed_plans(api_client, db, demo_user, stripe_mode):
    _checkout_and_activate(
        api_client, db, demo_user, "Pro",
        event_id="evt_acc_luna_checkout", session_id="cs_acc_luna", subscription_id="sub_acc_luna", customer_id="cus_acc_luna",
    )
    headers = auth_headers(demo_user)
    luna_quote = {"task_type": "luna_research", "requested_model": "gpt-5.6-luna"}

    # Pro is not in openai_luna_allowed_plans ("Max", "Enterprise").
    denied = api_client.post("/billing/quote", json=luna_quote, headers=headers)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "AGENT_MODEL_PLAN_REQUIRED"
    assert api_client.post("/billing/quote", json={"task_type": "default_chat", "requested_model": "default"}, headers=headers).status_code == 200

    # Upgrade Pro -> Max via subscription.updated: Luna unlocks immediately.
    upgraded = _post_signed_event(
        api_client,
        "evt_acc_luna_upgrade",
        "customer.subscription.updated",
        {
            "id": "sub_acc_luna",
            "customer": "cus_acc_luna",
            "status": "active",
            "cancel_at_period_end": False,
            "items": {"data": [{"price": {"id": PRICE_BY_PLAN["Max"]}}]},
        },
    )
    db.refresh(demo_user)
    assert upgraded.json()["processed"] is True
    assert demo_user.plan == "Max"
    allowed = api_client.post("/billing/quote", json=luna_quote, headers=headers)
    assert allowed.status_code == 200
    assert allowed.json()["estimated_min"] > 0

    # A payment failure restricts the effective plan and re-gates Luna.
    _post_signed_event(
        api_client,
        "evt_acc_luna_failed",
        "invoice.payment_failed",
        {"id": "in_acc_luna_failed", "customer": "cus_acc_luna", "subscription": "sub_acc_luna"},
    )
    gated = api_client.post("/billing/quote", json=luna_quote, headers=headers)
    assert gated.status_code == 403
    assert gated.json()["detail"]["code"] == "AGENT_MODEL_PLAN_REQUIRED"


# ---------------------------------------------------------------------------
# 6. Credits reserve/settle/refund never double-charge
# ---------------------------------------------------------------------------


def test_reserve_retry_is_idempotent_single_ledger_entry(db, normal_user):
    quote = quote_task(task_type="default_chat")
    starting_balance = normal_user.credit_balance

    first = reserve_task(db, normal_user.id, quote, "acceptance-reserve-retry")
    db.commit()
    second = reserve_task(db, normal_user.id, quote, "acceptance-reserve-retry")
    db.commit()
    db.refresh(normal_user)

    assert first == second
    assert normal_user.credit_balance == starting_balance - quote.credits
    assert db.query(CreditLedger).filter_by(idempotency_key="acceptance-reserve-retry").count() == 1
    reservation = db.query(CreditReservationRecord).filter_by(idempotency_key="acceptance-reserve-retry").one()
    assert reservation.status == "RESERVED"
    assert reservation.reserved_credits == quote.credits


def test_settle_retry_charges_exactly_once(db, normal_user):
    quote = quote_task(task_type="default_chat")
    starting_balance = normal_user.credit_balance
    reservation = reserve_task(db, normal_user.id, quote, "acceptance-settle-retry")
    db.commit()

    first = settle_task(db, normal_user.id, reservation, 1, metadata={"source": "server_usage"})
    db.commit()
    second = settle_task(db, normal_user.id, reservation, 1, metadata={"source": "server_retry"})
    db.commit()
    db.refresh(normal_user)

    assert (first.reserved, first.actual, first.adjustment) == (quote.credits, 1, quote.credits - 1)
    assert second == first
    assert normal_user.credit_balance == starting_balance - 1
    assert db.query(CreditSettlementRecord).count() == 1
    entries = db.query(CreditLedger).filter_by(user_id=normal_user.id).all()
    assert len(entries) == 2  # reservation consume + settlement refund
    assert sum(entry.credits_delta for entry in entries) == -1


def test_stream_failure_refund_restores_balance_exactly_once(db, normal_user):
    quote = quote_task(task_type="default_chat")
    starting_balance = normal_user.credit_balance
    reservation = reserve_task(db, normal_user.id, quote, "acceptance-stream-failure")
    db.commit()
    assert normal_user.credit_balance == starting_balance - quote.credits

    first = refund_task(db, normal_user.id, reservation, "STREAM_FAILED", metadata={"stream_id": "stream-1"})
    db.commit()
    second = refund_task(db, normal_user.id, reservation, "STREAM_FAILED_RETRY", metadata={"stream_id": "stream-1"})
    db.commit()
    db.refresh(normal_user)

    assert (first.reserved, first.actual, first.adjustment) == (quote.credits, 0, quote.credits)
    assert second == first
    assert normal_user.credit_balance == starting_balance
    assert db.query(CreditRefundEvent).count() == 1
    reservation_row = db.query(CreditReservationRecord).filter_by(idempotency_key="acceptance-stream-failure").one()
    assert reservation_row.status == "REFUNDED"
    entries = db.query(CreditLedger).filter_by(user_id=normal_user.id).all()
    assert len(entries) == 2  # reservation consume + full refund
    assert sum(entry.credits_delta for entry in entries) == 0


def test_settle_after_stream_refund_is_noop(db, normal_user):
    quote = quote_task(task_type="default_chat")
    starting_balance = normal_user.credit_balance
    reservation = reserve_task(db, normal_user.id, quote, "acceptance-refund-then-settle")
    db.commit()
    refund_task(db, normal_user.id, reservation, "STREAM_FAILED")
    db.commit()

    settlement = settle_task(db, normal_user.id, reservation, quote.credits)
    db.commit()
    db.refresh(normal_user)

    assert (settlement.reserved, settlement.actual, settlement.adjustment) == (quote.credits, 0, quote.credits)
    assert normal_user.credit_balance == starting_balance
    assert db.query(CreditSettlementRecord).count() == 0
    assert db.query(CreditLedger).filter_by(user_id=normal_user.id).count() == 2


# ---------------------------------------------------------------------------
# 7. Demo login: dev-only, rejected in production config
# ---------------------------------------------------------------------------


def test_demo_login_enabled_in_dev_config(api_client):
    login = api_client.post("/auth/mock-login", json={"email": "demo@puregamma.ai", "name": "Demo User"})
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "demo@puregamma.ai"
    assert api_client.get("/me").status_code == 200


def test_demo_fallback_enabled_in_dev_config(api_client, monkeypatch):
    from apps.api import dependencies

    monkeypatch.setattr(dependencies, "get_settings", lambda: Settings(auth_allow_demo_fallback=True))
    api_client.cookies.clear()

    response = api_client.get("/me")

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "demo@puregamma.ai"


def test_demo_login_disabled_in_production(api_client, monkeypatch):
    from apps.api import dependencies
    from apps.api.routers import auth as auth_router

    production = Settings(app_environment="production", auth_allow_demo_fallback=False)
    monkeypatch.setattr(auth_router, "get_settings", lambda: production)
    monkeypatch.setattr(dependencies, "get_settings", lambda: production)
    api_client.cookies.clear()

    login = api_client.post("/auth/mock-login", json={"email": "demo@puregamma.ai", "name": "Demo User"})
    fallback = api_client.get("/me")

    assert login.status_code == 404
    assert fallback.status_code == 401


def test_production_validation_rejects_demo_fallback():
    validate_production_settings(valid_production_settings())
    with pytest.raises(RuntimeError, match="AUTH_ALLOW_DEMO_FALLBACK"):
        validate_production_settings(replace(valid_production_settings(), auth_allow_demo_fallback=True))


# ---------------------------------------------------------------------------
# Task 4. notification_channels matrix per plan (digest orchestrator contract)
# ---------------------------------------------------------------------------


PLAN_CHANNELS = [
    ("Free", ["email", "push"]),
    ("Pro", ["telegram", "email", "push"]),
    ("Max", ["telegram", "slack", "email", "imessage", "push"]),
    ("Enterprise", ["telegram", "slack", "email", "imessage", "push"]),
]

CHANNEL_ALERT_ACTIONS = {
    "email_alert": "email",
    "telegram_alert": "telegram",
    "slack_alert": "slack",
    "imessage_alert": "imessage",
    "push_alert": "push",
}


@pytest.mark.parametrize(("plan", "channels"), PLAN_CHANNELS)
def test_notification_channels_matrix_per_plan(plan, channels):
    entitlement = entitlement_for_plan(plan)
    assert entitlement["notification_channels"] == channels
    for action, channel in CHANNEL_ALERT_ACTIONS.items():
        assert can_run_action(plan, action) is (channel in channels)


@pytest.mark.parametrize(("plan", "channels"), PLAN_CHANNELS)
def test_get_user_entitlement_channels_match_plan(db, user_factory, plan, channels):
    user = user_factory(f"{plan.lower().replace(' ', '-')}-channels@puregamma.ai", plan=plan)
    assert get_user_entitlement(db, user.id)["notification_channels"] == channels
