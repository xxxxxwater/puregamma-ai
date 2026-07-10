from __future__ import annotations

from tests.conftest import auth_headers


def test_non_admin_access_denied(api_client, normal_user):
    response = api_client.get("/admin/users", headers=auth_headers(normal_user))

    assert response.status_code == 403


def test_admin_can_read_users_webhooks_and_deliveries(api_client, admin_user):
    headers = auth_headers(admin_user)

    users = api_client.get("/admin/users", headers=headers)
    webhooks = api_client.get("/admin/stripe-events", headers=headers)
    stripe_products = api_client.get("/admin/stripe/products", headers=headers)
    billing_intents = api_client.get("/admin/billing-intents", headers=headers)
    deliveries = api_client.get("/admin/notifications", headers=headers)
    llm_status = api_client.get("/admin/llm-status", headers=headers)
    llm_calls = api_client.get("/admin/llm-calls", headers=headers)

    assert users.status_code == 200
    assert webhooks.status_code == 200
    assert stripe_products.status_code == 200
    assert billing_intents.status_code == 200
    assert deliveries.status_code == 200
    assert llm_status.status_code == 200
    assert llm_calls.status_code == 200
    assert "users" in users.json()
    assert "billing_intents" in billing_intents.json()
    assert "active_provider" in llm_status.json()
