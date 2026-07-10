from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.services.credit_service import grant_credits
from apps.api.services.entitlement_service import get_user_entitlement
from apps.api.services.notification_service import send_notification
from apps.api.services.stripe_service import StripeService
from apps.api.services.stripe_payment_link_service import create_payment_link_checkout as create_payment_link_checkout_for_user
from apps.api.services.stripe_payment_link_service import new_public_reference
from packages.billing.plans import get_plan
from packages.billing.stripe import allowed_checkout_plan, plan_for_price_id_or_none, price_id_for_plan
from packages.database.models import BillingCheckoutIntent, CreditLedger, StripeWebhookEvent, Subscription, SubscriptionPlan, User


logger = logging.getLogger(__name__)


class ManualReviewRequired(Exception):
    def __init__(self, message: str, intent: BillingCheckoutIntent | None = None):
        super().__init__(message)
        self.intent = intent


def dt_from_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def current_subscription(db: Session, user_id: str) -> Subscription | None:
    return (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )


def get_subscription(db: Session, user_id: str) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    sub = current_subscription(db, user_id)
    settings = get_settings()
    return {
        "plan": user.plan,
        "subscription_status": sub.status if sub else "inactive",
        "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        "cancel_at_period_end": bool(sub.cancel_at_period_end) if sub else False,
        "cancel_at": sub.current_period_end.isoformat() if sub and sub.cancel_at_period_end and sub.current_period_end else None,
        "credit_balance": user.credit_balance,
        "account": {"auth_provider": user.auth_provider, "avatar_url": user.avatar_url, "email": user.email},
        "entitlement": get_user_entitlement(db, user_id),
        "checkout_mode": settings.billing_checkout_mode,
        "payment_links": {
            plan: bool(link)
            for plan, link in settings.stripe_payment_link_by_plan.items()
        },
        "primary_payment_link_configured": bool(settings.stripe_payment_link_primary),
    }


def get_credits(db: Session, user_id: str) -> dict:
    user = db.get(User, user_id)
    history = (
        db.query(CreditLedger)
        .filter(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "credit_balance": user.credit_balance if user else 0,
        "usage_history": [
            {
                "id": item.id,
                "action": item.action,
                "credits_delta": item.credits_delta,
                "balance_after": item.balance_after,
                "metadata": item.metadata_json,
                "created_at": item.created_at.isoformat(),
            }
            for item in history
        ],
    }


def _obj_get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _obj_list(obj: Any) -> list:
    data = _obj_get(obj, "data", [])
    return list(data or [])


def _metadata_dict(obj: Any) -> dict:
    metadata = _obj_get(obj, "metadata", {}) or {}
    try:
        return dict(metadata)
    except Exception:
        return {}


def _plan_name_from_price(price: Any) -> str | None:
    metadata = _metadata_dict(price)
    candidate = metadata.get("plan_name") or _obj_get(price, "lookup_key")
    if isinstance(candidate, str):
        normalized = candidate.strip()
        if allowed_checkout_plan(normalized) or normalized == "Free":
            return normalized
        lowered = normalized.lower()
        for plan_name in ("Enterprise", "Max", "Pro", "Free"):
            if plan_name.lower() in lowered:
                return plan_name
    return None


def _price_monthly_amount(price: Any) -> float | None:
    amount = _obj_get(price, "unit_amount")
    if amount is None:
        decimal_amount = _obj_get(price, "unit_amount_decimal")
        try:
            amount = int(float(decimal_amount))
        except (TypeError, ValueError):
            return None
    try:
        return round(float(amount) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def serialize_subscription_plan(row: SubscriptionPlan) -> dict:
    return {
        "name": row.name,
        "monthly_price": row.monthly_price,
        "monthly_credits": row.monthly_credits,
        "max_daily_reports": row.max_daily_reports,
        "max_alerts": row.max_alerts,
        "allowed_data_sources": row.allowed_data_sources,
        "stripe_price_id": row.stripe_price_id,
        "is_active": row.is_active,
    }


def _sync_plan_from_stripe_price(db: Session, price: Any) -> SubscriptionPlan | None:
    plan_name = _plan_name_from_price(price)
    if not plan_name:
        return None
    plan_defaults = get_plan(plan_name)
    row = db.get(SubscriptionPlan, plan_name)
    if not row:
        row = SubscriptionPlan(
            name=plan_name,
            monthly_price=plan_defaults.monthly_price,
            monthly_credits=plan_defaults.monthly_credits,
            max_daily_reports=plan_defaults.max_daily_reports,
            max_alerts=plan_defaults.max_alerts,
            allowed_data_sources=list(plan_defaults.allowed_data_sources),
        )
        db.add(row)
    row.stripe_price_id = _obj_get(price, "id") or row.stripe_price_id
    row.monthly_price = _price_monthly_amount(price)
    row.is_active = bool(_obj_get(price, "active", True))
    db.flush()
    return row


def sync_stripe_products(db: Session) -> dict:
    settings = get_settings()
    if settings.billing_mode != "stripe" or not settings.stripe_secret_key:
        rows = db.query(SubscriptionPlan).order_by(SubscriptionPlan.name).all()
        return {"mode": "mock", "synced": 0, "skipped": 0, "plans": [serialize_subscription_plan(row) for row in rows]}
    stripe = StripeService(settings)._client()
    products = _obj_list(stripe.Product.list(active=True, limit=100))
    prices = _obj_list(stripe.Price.list(active=True, limit=100))
    synced: list[dict] = []
    skipped: list[str] = []
    for price in prices:
        row = _sync_plan_from_stripe_price(db, price)
        if row:
            synced.append(serialize_subscription_plan(row))
        else:
            skipped.append(_obj_get(price, "id", "unknown"))
    db.commit()
    return {"mode": "stripe", "products_seen": len(products), "prices_seen": len(prices), "synced": len(synced), "skipped": len(skipped), "plans": synced, "skipped_price_ids": skipped}


def stripe_products_status(db: Session) -> dict:
    local_rows = {row.name: serialize_subscription_plan(row) for row in db.query(SubscriptionPlan).order_by(SubscriptionPlan.name).all()}
    settings = get_settings()
    if settings.billing_mode != "stripe" or not settings.stripe_secret_key:
        return {
            "mode": "mock",
            "stripe_available": False,
            "items": [{"plan_name": name, "status": "local_only", "local": row, "stripe": None} for name, row in local_rows.items()],
        }
    stripe = StripeService(settings)._client()
    prices = _obj_list(stripe.Price.list(active=True, limit=100))
    remote: dict[str, dict] = {}
    for price in prices:
        plan_name = _plan_name_from_price(price)
        if not plan_name:
            continue
        remote[plan_name] = {
            "stripe_price_id": _obj_get(price, "id"),
            "monthly_price": _price_monthly_amount(price),
            "is_active": bool(_obj_get(price, "active", True)),
        }
    items = []
    for plan_name in sorted(set(local_rows) | set(remote)):
        local = local_rows.get(plan_name)
        stripe_row = remote.get(plan_name)
        if local and stripe_row:
            status = "in_sync" if local["stripe_price_id"] == stripe_row["stripe_price_id"] and local["monthly_price"] == stripe_row["monthly_price"] and local["is_active"] == stripe_row["is_active"] else "mismatch"
        elif local:
            status = "local_only"
        else:
            status = "stripe_only"
        items.append({"plan_name": plan_name, "status": status, "local": local, "stripe": stripe_row})
    return {"mode": "stripe", "stripe_available": True, "items": items}


def create_checkout_session(db: Session, user_id: str, plan_name: str) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    if not allowed_checkout_plan(plan_name):
        raise ValueError(f"Unsupported checkout plan: {plan_name}")
    price_id = price_id_for_plan(plan_name)
    intent = BillingCheckoutIntent(
        public_reference=new_public_reference(),
        user_id=user.id,
        plan_name=plan_name,
        checkout_mode="session",
        stripe_price_id=price_id,
        status="created",
        metadata_json={"source": "checkout_session"},
    )
    db.add(intent)
    db.flush()
    return StripeService().create_checkout_session(db, user, plan_name, intent)


def create_payment_link_checkout(db: Session, user_id: str, plan_name: str) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    return create_payment_link_checkout_for_user(db, user, plan_name)


def serialize_checkout_intent(intent: BillingCheckoutIntent) -> dict:
    return {
        "id": intent.id,
        "public_reference": intent.public_reference,
        "user_id": intent.user_id,
        "plan_name": intent.plan_name,
        "checkout_mode": intent.checkout_mode,
        "stripe_payment_link_url": intent.stripe_payment_link_url,
        "stripe_checkout_session_id": intent.stripe_checkout_session_id,
        "stripe_customer_id": intent.stripe_customer_id,
        "stripe_price_id": intent.stripe_price_id,
        "status": intent.status,
        "metadata": intent.metadata_json,
        "created_at": intent.created_at.isoformat(),
        "completed_at": intent.completed_at.isoformat() if intent.completed_at else None,
    }


def resolve_checkout_intent(db: Session, intent_id: str, user_id: str, plan_name: str, admin_id: str) -> dict:
    if not allowed_checkout_plan(plan_name):
        raise ValueError(f"Unsupported checkout plan: {plan_name}")
    intent = db.get(BillingCheckoutIntent, intent_id)
    if not intent:
        raise ValueError("BillingCheckoutIntent not found")
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    plan = get_plan(plan_name)
    upsert_subscription(
        db,
        user,
        stripe_subscription_id=intent.stripe_checkout_session_id or f"manual_{intent.public_reference}",
        stripe_customer_id=intent.stripe_customer_id or user.stripe_customer_id,
        stripe_price_id=intent.stripe_price_id or price_id_for_plan(plan.name),
        plan_name=plan.name,
        status="active",
    )
    existing = (
        db.query(CreditLedger)
        .filter(CreditLedger.user_id == user.id, CreditLedger.action == "monthly_credit_grant", CreditLedger.metadata_json["manual_resolve_intent_id"].as_string() == intent.id)
        .first()
    )
    if not existing:
        grant_credits(db, user.id, "monthly_credit_grant", plan.monthly_credits, {"source": "admin_manual_resolve", "manual_resolve_intent_id": intent.id, "admin_id": admin_id, "plan": plan.name})
    intent.user_id = user.id
    intent.plan_name = plan.name
    intent.status = "completed"
    intent.completed_at = datetime.now(timezone.utc)
    intent.metadata_json = {**(intent.metadata_json or {}), "resolved_by_admin_id": admin_id}
    db.commit()
    return serialize_checkout_intent(intent)


def create_portal_session(db: Session, user_id: str) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    return StripeService().create_portal_session(user)


def _sync_cancel_preference(user: User, sub: Subscription) -> None:
    if user.preference:
        user.preference.subscription_cancel_at_period_end = bool(sub.cancel_at_period_end)
        user.preference.subscription_cancel_at = sub.current_period_end if sub.cancel_at_period_end else None


def set_subscription_cancel_at_period_end(db: Session, user_id: str, cancel_at_period_end: bool) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    sub = current_subscription(db, user_id)
    if not sub or not sub.stripe_subscription_id:
        raise ValueError("User does not have an active Stripe subscription")
    remote = StripeService().modify_subscription_cancel_at_period_end(sub.stripe_subscription_id, cancel_at_period_end)
    sub.cancel_at_period_end = bool(remote.get("cancel_at_period_end", cancel_at_period_end))
    sub.status = remote.get("status", sub.status) or sub.status
    sub.current_period_start = dt_from_ts(remote.get("current_period_start")) or sub.current_period_start
    sub.current_period_end = dt_from_ts(remote.get("current_period_end")) or sub.current_period_end
    _sync_cancel_preference(user, sub)
    db.commit()
    return get_subscription(db, user_id)


def upsert_subscription(
    db: Session,
    user: User,
    *,
    stripe_subscription_id: str | None,
    stripe_customer_id: str | None,
    stripe_price_id: str | None,
    plan_name: str,
    status: str,
    current_period_start: datetime | None = None,
    current_period_end: datetime | None = None,
    cancel_at_period_end: bool = False,
) -> Subscription:
    sub = None
    if stripe_subscription_id:
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == stripe_subscription_id).one_or_none()
    if not sub:
        sub = current_subscription(db, user.id)
    if not sub:
        sub = Subscription(user_id=user.id)
        db.add(sub)
    sub.stripe_subscription_id = stripe_subscription_id or sub.stripe_subscription_id
    sub.stripe_customer_id = stripe_customer_id or sub.stripe_customer_id
    sub.stripe_price_id = stripe_price_id or sub.stripe_price_id
    sub.plan_name = plan_name
    sub.status = status
    sub.current_period_start = current_period_start or sub.current_period_start
    sub.current_period_end = current_period_end or sub.current_period_end
    sub.cancel_at_period_end = cancel_at_period_end
    user.plan = plan_name if status not in {"canceled", "deleted"} else "Free"
    if stripe_customer_id:
        user.stripe_customer_id = stripe_customer_id
    _sync_cancel_preference(user, sub)
    db.flush()
    return sub


def mock_upgrade(db: Session, user_id: str, plan_name: str) -> dict:
    settings = get_settings()
    if settings.billing_mode != "mock":
        raise ValueError("mock-upgrade is only available when BILLING_MODE=mock")
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    plan = get_plan(plan_name)
    price_id = price_id_for_plan(plan_name, settings)
    upsert_subscription(
        db,
        user,
        stripe_subscription_id=f"sub_mock_{user.id[:8]}",
        stripe_customer_id=user.stripe_customer_id or f"cus_mock_{user.id[:8]}",
        stripe_price_id=price_id,
        plan_name=plan.name,
        status="active",
    )
    grant_credits(db, user.id, "monthly_credit_grant", plan.monthly_credits, {"source": "mock_upgrade", "plan": plan.name})
    db.commit()
    return get_subscription(db, user_id)


def _extract_subscription_price_id(subscription: dict) -> str | None:
    items = subscription.get("items", {}).get("data", [])
    if items:
        return items[0].get("price", {}).get("id")
    return subscription.get("plan", {}).get("id") or subscription.get("price", {}).get("id")


def _extract_session_price_id(session: dict) -> str | None:
    line_items = session.get("line_items", {}).get("data", [])
    if line_items:
        return line_items[0].get("price", {}).get("id")
    return session.get("price_id")


def _intent_by_session(db: Session, obj: dict) -> BillingCheckoutIntent | None:
    client_reference_id = obj.get("client_reference_id")
    if client_reference_id:
        intent = db.query(BillingCheckoutIntent).filter(BillingCheckoutIntent.public_reference == client_reference_id).one_or_none()
        if intent:
            return intent
    metadata = obj.get("metadata") or {}
    checkout_intent_id = metadata.get("checkout_intent_id")
    if checkout_intent_id:
        return db.get(BillingCheckoutIntent, checkout_intent_id)
    session_id = obj.get("id")
    if session_id:
        return db.query(BillingCheckoutIntent).filter(BillingCheckoutIntent.stripe_checkout_session_id == session_id).one_or_none()
    return None


def _user_by_metadata_or_customer(db: Session, obj: dict) -> User | None:
    metadata = obj.get("metadata") or {}
    user_id = metadata.get("user_id")
    if user_id:
        return db.get(User, user_id)
    customer_id = obj.get("customer")
    if customer_id:
        return db.query(User).filter(User.stripe_customer_id == customer_id).one_or_none()
    return None


def _mark_intent_manual_review(db: Session, intent: BillingCheckoutIntent | None, message: str) -> None:
    if intent:
        intent.status = "requires_manual_review"
        intent.metadata_json = {**(intent.metadata_json or {}), "manual_review_reason": message}
        db.flush()


def _resolve_plan_name(db: Session, obj: dict, intent: BillingCheckoutIntent | None, price_id: str | None) -> str:
    metadata = obj.get("metadata") or {}
    metadata_plan = metadata.get("plan_name")
    if metadata_plan and allowed_checkout_plan(metadata_plan):
        return metadata_plan
    price_plan = plan_for_price_id_or_none(price_id)
    if price_plan:
        return price_plan
    if intent and allowed_checkout_plan(intent.plan_name):
        if (intent.metadata_json or {}).get("used_primary_payment_link"):
            raise ManualReviewRequired("Payment Link primary URL cannot determine plan without price_id or metadata.", intent)
        return intent.plan_name
    raise ManualReviewRequired("Unable to map Stripe checkout to a PureGamma plan.", intent)


def _retrieve_session_line_items(obj: dict) -> dict:
    settings = get_settings()
    if settings.billing_mode != "stripe" or obj.get("line_items"):
        return obj
    session_id = obj.get("id")
    if not session_id:
        return obj
    try:
        line_items = StripeService(settings)._client().checkout.Session.list_line_items(session_id, limit=1)
    except Exception:
        return obj
    return {**obj, "line_items": {"data": list(line_items.get("data", []))}}


def _handle_checkout_completed(db: Session, obj: dict) -> None:
    obj = _retrieve_session_line_items(obj)
    intent = _intent_by_session(db, obj)
    user = db.get(User, intent.user_id) if intent else _user_by_metadata_or_customer(db, obj)
    if not user:
        _mark_intent_manual_review(db, intent, "checkout.session.completed missing known user")
        raise ManualReviewRequired("checkout.session.completed missing known user", intent)
    settings = get_settings()
    if settings.billing_mode == "stripe":
        subscription_id = obj.get("subscription")
        payment_status = obj.get("payment_status")
        if payment_status not in {None, "paid", "no_payment_required"}:
            return
        if subscription_id:
            stripe_sub = StripeService(settings)._client().Subscription.retrieve(subscription_id)
            if stripe_sub.get("status") not in {"active", "trialing"}:
                return
    price_id = _extract_session_price_id(obj) or (intent.stripe_price_id if intent else None)
    plan_name = _resolve_plan_name(db, obj, intent, price_id)
    plan = get_plan(plan_name)
    upsert_subscription(
        db,
        user,
        stripe_subscription_id=obj.get("subscription"),
        stripe_customer_id=obj.get("customer"),
        stripe_price_id=price_id or price_id_for_plan(plan.name),
        plan_name=plan.name,
        status="active",
    )
    if intent:
        intent.status = "completed"
        intent.completed_at = datetime.now(timezone.utc)
        intent.stripe_checkout_session_id = obj.get("id") or intent.stripe_checkout_session_id
        intent.stripe_customer_id = obj.get("customer") or intent.stripe_customer_id
        intent.stripe_price_id = price_id or intent.stripe_price_id
    subscription_id = obj.get("subscription")
    existing = (
        db.query(CreditLedger)
        .filter(CreditLedger.user_id == user.id, CreditLedger.action == "monthly_credit_grant", CreditLedger.metadata_json["subscription_id"].as_string() == subscription_id)
        .first()
        if subscription_id
        else None
    )
    if not existing:
        grant_credits(db, user.id, "monthly_credit_grant", plan.monthly_credits, {"source": "checkout.session.completed", "plan": plan.name, "subscription_id": subscription_id})


def _handle_subscription_upsert(db: Session, obj: dict) -> None:
    user = _user_by_metadata_or_customer(db, obj)
    if not user:
        customer_id = obj.get("customer")
        user = db.query(User).filter(User.stripe_customer_id == customer_id).one_or_none()
    if not user:
        raise ValueError("subscription event missing known user")
    price_id = _extract_subscription_price_id(obj)
    metadata_plan = (obj.get("metadata") or {}).get("plan_name")
    plan_name = metadata_plan if metadata_plan and allowed_checkout_plan(metadata_plan) else plan_for_price_id_or_none(price_id)
    if not plan_name:
        raise ManualReviewRequired("Unable to map Stripe subscription price to a PureGamma plan.")
    upsert_subscription(
        db,
        user,
        stripe_subscription_id=obj.get("id"),
        stripe_customer_id=obj.get("customer"),
        stripe_price_id=price_id,
        plan_name=plan_name,
        status=obj.get("status", "active"),
        current_period_start=dt_from_ts(obj.get("current_period_start")),
        current_period_end=dt_from_ts(obj.get("current_period_end")),
        cancel_at_period_end=bool(obj.get("cancel_at_period_end", False)),
    )


def _handle_subscription_deleted(db: Session, obj: dict) -> None:
    _handle_subscription_upsert(db, {**obj, "status": "deleted"})


def _handle_invoice_paid(db: Session, obj: dict) -> None:
    billing_reason = obj.get("billing_reason")
    if billing_reason != "subscription_cycle":
        return
    invoice_id = obj.get("id")
    if invoice_id:
        existing = (
            db.query(CreditLedger)
            .filter(CreditLedger.action == "monthly_credit_grant", CreditLedger.metadata_json["invoice_id"].as_string() == invoice_id)
            .first()
        )
        if existing:
            return
    user = _user_by_metadata_or_customer(db, obj)
    subscription_id = obj.get("subscription")
    if not user and subscription_id:
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == subscription_id).one_or_none()
        user = db.get(User, sub.user_id) if sub else None
    if not user:
        return
    sub = current_subscription(db, user.id)
    price_id = None
    lines = obj.get("lines", {}).get("data", [])
    if lines:
        price_id = lines[0].get("price", {}).get("id")
    plan_name = plan_for_price_id_or_none(price_id) or (sub.plan_name if sub else user.plan)
    plan = get_plan(plan_name)
    grant_credits(db, user.id, "monthly_credit_grant", plan.monthly_credits, {"source": "invoice.paid", "invoice_id": invoice_id, "plan": plan.name})


def _handle_invoice_payment_failed(db: Session, obj: dict) -> None:
    user = _user_by_metadata_or_customer(db, obj)
    subscription_id = obj.get("subscription")
    if not user and subscription_id:
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == subscription_id).one_or_none()
        user = db.get(User, sub.user_id) if sub else None
    if not user:
        return
    sub = current_subscription(db, user.id)
    if sub:
        sub.status = "past_due"
    db.flush()


def _handle_price_upsert(db: Session, obj: dict) -> None:
    row = _sync_plan_from_stripe_price(db, obj)
    if row:
        logger.info("stripe_price_synced plan=%s price_id=%s", row.name, row.stripe_price_id)
    else:
        logger.info("stripe_price_skipped price_id=%s", obj.get("id"))


def _handle_product_event(obj: dict) -> None:
    logger.info("stripe_product_event product_id=%s name=%s active=%s", obj.get("id"), obj.get("name"), obj.get("active"))


def _handle_trial_will_end(db: Session, obj: dict) -> None:
    user = _user_by_metadata_or_customer(db, obj)
    if not user and obj.get("id"):
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == obj.get("id")).one_or_none()
        user = db.get(User, sub.user_id) if sub else None
    if not user:
        return
    message = "Your PureGamma.ai trial will end soon. Review your subscription settings in Billing. This is not financial advice."
    try:
        send_notification(db, user.id, "email", message, {"source": "customer.subscription.trial_will_end", "subscription_id": obj.get("id")})
    except Exception as exc:
        logger.warning("stripe_trial_will_end_notification_failed user_id=%s error=%s", user.id, exc)


def _handle_payment_intent_succeeded(obj: dict) -> None:
    logger.info("stripe_payment_intent_succeeded payment_intent_id=%s customer=%s amount=%s", obj.get("id"), obj.get("customer"), obj.get("amount_received") or obj.get("amount"))


def _handle_payment_intent_failed(db: Session, obj: dict) -> None:
    metadata = obj.get("metadata") or {}
    _handle_invoice_payment_failed(db, {"customer": obj.get("customer"), "subscription": metadata.get("subscription_id") or obj.get("subscription")})
    logger.info("stripe_payment_intent_failed payment_intent_id=%s customer=%s", obj.get("id"), obj.get("customer"))


def _handle_charge_refunded(obj: dict) -> None:
    logger.info("stripe_charge_refunded charge_id=%s payment_intent=%s amount_refunded=%s", obj.get("id"), obj.get("payment_intent"), obj.get("amount_refunded"))


def process_stripe_event(db: Session, event: dict, raw_payload: bytes) -> dict:
    event_id = event.get("id")
    event_type = event.get("type")
    if not event_id or not event_type:
        raise ValueError("Stripe event requires id and type")
    raw_hash = hashlib.sha256(raw_payload).hexdigest()
    existing = db.query(StripeWebhookEvent).filter(StripeWebhookEvent.stripe_event_id == event_id).one_or_none()
    if existing and existing.processed:
        return {"processed": False, "duplicate": True, "event_type": existing.event_type}
    row = existing or StripeWebhookEvent(stripe_event_id=event_id, event_type=event_type, raw_payload_hash=raw_hash)
    if not existing:
        db.add(row)
        db.flush()
    obj = (event.get("data") or {}).get("object") or {}
    try:
        if event_type == "checkout.session.completed":
            _handle_checkout_completed(db, obj)
        elif event_type in {"customer.subscription.created", "customer.subscription.updated"}:
            _handle_subscription_upsert(db, obj)
        elif event_type == "customer.subscription.deleted":
            _handle_subscription_deleted(db, obj)
        elif event_type == "invoice.paid":
            _handle_invoice_paid(db, obj)
        elif event_type == "invoice.payment_failed":
            _handle_invoice_payment_failed(db, obj)
        elif event_type == "checkout.session.expired":
            intent = _intent_by_session(db, obj)
            if intent:
                intent.status = "expired"
        elif event_type in {"price.created", "price.updated"}:
            _handle_price_upsert(db, obj)
        elif event_type in {"product.created", "product.updated"}:
            _handle_product_event(obj)
        elif event_type == "customer.subscription.trial_will_end":
            _handle_trial_will_end(db, obj)
        elif event_type == "payment_intent.succeeded":
            _handle_payment_intent_succeeded(obj)
        elif event_type == "payment_intent.payment_failed":
            _handle_payment_intent_failed(db, obj)
        elif event_type == "charge.refunded":
            _handle_charge_refunded(obj)
        row.processed = True
        row.processed_at = datetime.now(timezone.utc)
    except ManualReviewRequired as exc:
        row.processed = True
        row.requires_manual_review = True
        row.error_message = str(exc)
        row.processed_at = datetime.now(timezone.utc)
        _mark_intent_manual_review(db, exc.intent, str(exc))
    except Exception as exc:
        row.error_message = str(exc)
        raise
    db.commit()
    return {"processed": True, "duplicate": False, "event_type": event_type, "requires_manual_review": row.requires_manual_review}


def parse_event_payload(raw_payload: bytes) -> dict:
    return json.loads(raw_payload.decode("utf-8"))
