from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from apps.api.config import Settings, get_settings
from packages.billing.stripe import price_id_for_plan
from packages.database.models import BillingCheckoutIntent, GatewayTopupIntent, User


class StripeService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _client(self):
        try:
            import stripe
        except ImportError as exc:
            raise RuntimeError("stripe package is required when BILLING_MODE=stripe") from exc
        stripe.api_key = self.settings.stripe_secret_key
        stripe.api_version = self.settings.stripe_api_version
        return stripe

    def create_customer_if_needed(self, db: Session, user: User) -> str:
        if user.stripe_customer_id:
            return user.stripe_customer_id
        if self.settings.billing_mode == "mock":
            user.stripe_customer_id = f"cus_mock_{user.id[:8]}"
            db.flush()
            return user.stripe_customer_id
        stripe = self._client()
        customer = stripe.Customer.create(email=user.email, name=user.name, metadata={"user_id": user.id})
        user.stripe_customer_id = customer["id"]
        db.flush()
        return user.stripe_customer_id

    def create_checkout_session(self, db: Session, user: User, plan_name: str, intent: BillingCheckoutIntent | None = None) -> dict:
        price_id = price_id_for_plan(plan_name, self.settings)
        customer_id = self.create_customer_if_needed(db, user)
        if self.settings.billing_mode == "mock":
            session_id = f"cs_mock_{uuid.uuid4().hex}"
            if intent:
                intent.stripe_checkout_session_id = session_id
                intent.stripe_customer_id = customer_id
                intent.stripe_price_id = price_id
                db.flush()
            return {
                "checkout_url": f"{self.settings.site_url.rstrip('/')}/billing/mock-checkout?session=mock&plan={plan_name}",
                "mode": "mock",
                "checkout_mode": "payment_link",
                "checkout_intent_id": intent.id if intent else None,
                "client_reference_id": intent.public_reference if intent else None,
                "price_id": price_id,
            }
        stripe = self._client()
        metadata = {"user_id": user.id, "plan_name": plan_name}
        if intent:
            metadata["checkout_intent_id"] = intent.id
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=self.settings.stripe_success_url,
            cancel_url=self.settings.stripe_cancel_url,
            client_reference_id=intent.public_reference if intent else None,
            metadata=metadata,
            subscription_data={"metadata": metadata},
        )
        if intent:
            intent.stripe_checkout_session_id = session["id"]
            intent.stripe_customer_id = customer_id
            intent.stripe_price_id = price_id
            db.flush()
        return {
            "checkout_url": session["url"],
            "mode": "stripe",
            "checkout_mode": "session",
            "checkout_intent_id": intent.id if intent else None,
            "client_reference_id": intent.public_reference if intent else None,
            "price_id": price_id,
        }

    def create_gateway_topup_session(self, db: Session, user: User, intent: GatewayTopupIntent, *, locale: str) -> dict:
        """Create a one-time, exact-amount Checkout Session for API credit.

        This deliberately uses ``mode=payment`` rather than the existing
        subscription flow. The shared Stripe Customer is useful for receipts
        and payment methods, but no subscription is created or modified.
        """

        customer_id = self.create_customer_if_needed(db, user)
        if self.settings.billing_mode == "mock":
            session_id = f"cs_mock_gateway_{uuid.uuid4().hex}"
            intent.stripe_checkout_session_id = session_id
            intent.stripe_customer_id = customer_id
            db.flush()
            return {
                "checkout_url": f"{self.settings.site_url.rstrip('/')}/{locale}/gateway?topup=mock",
                "mode": "mock",
                "checkout_mode": "gateway_topup",
                "stripe_checkout_session_id": session_id,
            }

        metadata = {
            "purpose": "gateway_topup",
            "gateway_topup_intent_id": intent.id,
            "user_id": user.id,
            "amount_cents": str(intent.amount_cents),
            "currency": intent.currency,
        }
        redirect_base = f"{self.settings.site_url.rstrip('/')}/{locale}/gateway"
        stripe = self._client()
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": intent.currency.lower(),
                        "product_data": {
                            "name": "PureGamma API Gateway prepaid balance",
                            "description": "Prepaid USD balance for PureGamma API Gateway usage",
                        },
                        "unit_amount": intent.amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{redirect_base}?topup=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{redirect_base}?topup=cancelled",
            client_reference_id=intent.public_reference,
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
        )
        intent.stripe_checkout_session_id = session["id"]
        intent.stripe_customer_id = customer_id
        db.flush()
        return {
            "checkout_url": session["url"],
            "mode": "stripe",
            "checkout_mode": "gateway_topup",
            "stripe_checkout_session_id": session["id"],
        }

    def create_portal_session(self, user: User) -> dict:
        if not user.stripe_customer_id:
            raise ValueError("User does not have a Stripe customer")
        if self.settings.billing_mode == "mock":
            return {"portal_url": f"{self.settings.site_url.rstrip('/')}/billing", "mode": "mock"}
        stripe = self._client()
        portal = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{self.settings.site_url}/billing",
        )
        return {"portal_url": portal["url"], "mode": "stripe"}

    def modify_subscription_cancel_at_period_end(self, subscription_id: str, cancel_at_period_end: bool) -> dict:
        if self.settings.billing_mode == "mock":
            return {"id": subscription_id, "cancel_at_period_end": cancel_at_period_end, "status": "active"}
        stripe = self._client()
        return dict(stripe.Subscription.modify(subscription_id, cancel_at_period_end=cancel_at_period_end))
