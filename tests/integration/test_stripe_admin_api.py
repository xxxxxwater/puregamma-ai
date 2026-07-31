from __future__ import annotations

import types

from apps.api.config import Settings
from apps.api.services import billing_service
from packages.database.models import SubscriptionPlan
from tests.conftest import auth_headers


class FakeStripeService:
    def __init__(self, settings=None):
        self.settings = settings

    def _client(self):
        return types.SimpleNamespace(
            Product=types.SimpleNamespace(list=lambda **kwargs: {"data": [{"id": "prod_pro", "name": "PureGamma Pro", "active": True}]}),
            Price=types.SimpleNamespace(
                list=lambda **kwargs: {
                    "data": [
                        {"id": "price_live_pro", "lookup_key": "puregamma_pro_monthly", "unit_amount": 2990, "active": True, "metadata": {"plan_name": "Pro"}}
                    ]
                }
            ),
        )


def test_admin_stripe_products_sync(api_client, db, admin_user, monkeypatch):
    monkeypatch.setattr(billing_service, "get_settings", lambda: Settings(billing_mode="stripe", stripe_secret_key="sk_test"))
    monkeypatch.setattr(billing_service, "StripeService", FakeStripeService)

    response = api_client.post("/admin/stripe/products/sync", headers=auth_headers(admin_user))
    status = api_client.get("/admin/stripe/products", headers=auth_headers(admin_user))
    plan = db.get(SubscriptionPlan, "Pro")

    assert response.status_code == 200
    assert response.json()["synced"] == 1
    assert plan.stripe_price_id == "price_live_pro"
    assert plan.monthly_price == 29.9
    assert status.status_code == 200
    assert any(item["plan_name"] == "Pro" for item in status.json()["items"])


def test_non_admin_cannot_sync_stripe_products(api_client, normal_user):
    response = api_client.post("/admin/stripe/products/sync", headers=auth_headers(normal_user))

    assert response.status_code == 403
