from __future__ import annotations

import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.orm import Session

from apps.api.config import Settings, get_settings
from packages.billing.stripe import allowed_checkout_plan, payment_link_for_plan
from packages.database.models import BillingCheckoutIntent, User


def new_public_reference() -> str:
    return f"pgci_{uuid.uuid4().hex}"


def append_query_params(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def create_payment_link_checkout(
    db: Session,
    user: User,
    plan_name: str,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    if not allowed_checkout_plan(plan_name):
        raise ValueError(f"Unsupported checkout plan: {plan_name}")

    public_reference = new_public_reference()

    if settings.billing_mode == "mock":
        # Mock mode must never hand out a live Stripe payment page; route to
        # the in-app mock checkout instead.
        checkout_url = f"{settings.site_url.rstrip('/')}/billing/mock-checkout?session=mock&plan={plan_name}&client_reference_id={public_reference}"
        link = ""
        used_primary = True
    else:
        link = payment_link_for_plan(plan_name, settings)
        used_primary = False
        if not link:
            if settings.stripe_payment_link_primary and user.role == "admin":
                link = settings.stripe_payment_link_primary
                used_primary = True
            else:
                raise ValueError("Stripe Payment Link is not configured for this plan.")
        checkout_url = append_query_params(
            link,
            {
                "client_reference_id": public_reference,
                "utm_source": "puregamma",
                "utm_medium": "billing",
                "utm_campaign": plan_name,
            },
        )

    intent = BillingCheckoutIntent(
        public_reference=public_reference,
        user_id=user.id,
        plan_name=plan_name,
        checkout_mode="payment_link",
        stripe_payment_link_url=link,
        status="created",
        metadata_json={
            "used_primary_payment_link": used_primary,
            "payment_link_plan_mapping": "unknown" if used_primary else "plan_specific",
        },
    )
    db.add(intent)
    db.flush()

    return {
        "checkout_url": checkout_url,
        "checkout_mode": "payment_link",
        "checkout_intent_id": intent.id,
        "client_reference_id": public_reference,
        "payment_link_plan_mapping": intent.metadata_json["payment_link_plan_mapping"],
    }
