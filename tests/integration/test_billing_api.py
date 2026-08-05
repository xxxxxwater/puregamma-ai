from __future__ import annotations

from apps.api.services.billing_service import mock_upgrade
from packages.database.models import User
from tests.conftest import auth_headers


def test_billing_subscription_and_credits_api(api_client, demo_user: User):
    headers = auth_headers(demo_user)

    subscription = api_client.get("/billing/subscription", headers=headers)
    credits = api_client.get("/billing/credits", headers=headers)

    assert subscription.status_code == 200
    assert subscription.json()["plan"] == "Free"
    assert credits.status_code == 200
    assert credits.json()["credit_balance"] == 150


def test_checkout_session_rejects_unsupported_plan(api_client, demo_user: User):
    response = api_client.post("/billing/create-checkout-session", json={"plan_name": "ForgedMax"}, headers=auth_headers(demo_user))

    assert response.status_code == 400
    assert "Unsupported checkout plan" in response.json()["detail"]


def test_mock_upgrade_grants_plan_credits_once_per_call(api_client, db, demo_user: User):
    response = api_client.post("/billing/mock-upgrade", json={"plan_name": "Pro"}, headers=auth_headers(demo_user))

    db.refresh(demo_user)
    assert response.status_code == 200
    assert response.json()["plan"] == "Pro"
    assert demo_user.credit_balance == 3150


def test_user_cannot_read_other_users_billing(api_client, normal_user: User, max_user: User):
    response = api_client.get("/billing/subscription", headers=auth_headers(normal_user))

    assert response.status_code == 200
    assert response.json()["plan"] == normal_user.plan
    assert response.json()["plan"] != max_user.plan


def test_cancel_and_reactivate_subscription_api(api_client, db, demo_user: User):
    mock_upgrade(db, demo_user.id, "Pro")
    headers = auth_headers(demo_user)

    canceled = api_client.post("/billing/cancel-subscription", headers=headers)
    reactivated = api_client.post("/billing/reactivate-subscription", headers=headers)

    assert canceled.status_code == 200
    assert canceled.json()["cancel_at_period_end"] is True
    assert reactivated.status_code == 200
    assert reactivated.json()["cancel_at_period_end"] is False
