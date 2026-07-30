"""Prepaid wallet operations for the public PureGamma API Gateway.

The Gateway wallet is intentionally isolated from the existing PureGamma
subscription and Credits systems. All balance mutations are ledgered and
idempotent so a repeated Stripe delivery cannot ever credit a user twice.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.services.stripe_service import StripeService
from packages.database.models import (
    GatewayRequestLog,
    GatewayTopupIntent,
    GatewayWallet,
    GatewayWalletLedger,
    User,
)
from packages.gateway.contracts import GatewayProviderError


USD_SCALE = Decimal("0.00000001")
CENTS_PER_USD = Decimal("100")


class GatewayTopupError(ValueError):
    """A safe message/code pair for a user-initiated wallet checkout."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _usd(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(USD_SCALE, rounding=ROUND_HALF_UP)


def topup_amount_to_cents(amount_usd: Decimal | int | float | str) -> int:
    """Validate an exact-cent USD user amount against configured bounds."""

    try:
        amount = Decimal(str(amount_usd))
    except (InvalidOperation, ValueError) as exc:
        raise GatewayTopupError("GATEWAY_TOPUP_AMOUNT_INVALID", "Top-up amount must be a valid USD amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise GatewayTopupError("GATEWAY_TOPUP_AMOUNT_INVALID", "Top-up amount must be greater than zero")
    cents = amount * CENTS_PER_USD
    if cents != cents.to_integral_value():
        raise GatewayTopupError("GATEWAY_TOPUP_AMOUNT_PRECISION", "Top-up amount must have at most two decimal places")
    value = int(cents)
    settings = get_settings()
    if settings.gateway_topup_min_usd_cents <= 0 or settings.gateway_topup_max_usd_cents < settings.gateway_topup_min_usd_cents:
        raise GatewayTopupError("GATEWAY_TOPUP_CONFIGURATION_INVALID", "Gateway top-up limits are not configured")
    if value < settings.gateway_topup_min_usd_cents or value > settings.gateway_topup_max_usd_cents:
        minimum = Decimal(settings.gateway_topup_min_usd_cents) / CENTS_PER_USD
        maximum = Decimal(settings.gateway_topup_max_usd_cents) / CENTS_PER_USD
        raise GatewayTopupError("GATEWAY_TOPUP_AMOUNT_OUT_OF_RANGE", f"Top-up amount must be between ${minimum:.2f} and ${maximum:.2f}")
    return value


def gateway_wallet(db: Session, user_id: str, *, lock: bool = False) -> GatewayWallet:
    query = db.query(GatewayWallet).filter_by(user_id=user_id)
    if lock:
        query = query.with_for_update()
    wallet = query.one_or_none()
    if wallet is None:
        wallet = GatewayWallet(user_id=user_id, currency="USD")
        db.add(wallet)
        db.flush()
    return wallet


def serialize_gateway_wallet(wallet: GatewayWallet) -> dict[str, str]:
    return {
        "currency": wallet.currency,
        "available_balance_usd": str(_usd(wallet.available_balance_usd or 0)),
        "lifetime_credited_usd": str(_usd(wallet.lifetime_credited_usd or 0)),
        "lifetime_debited_usd": str(_usd(wallet.lifetime_debited_usd or 0)),
    }


def serialize_gateway_wallet_ledger(row: GatewayWalletLedger) -> dict[str, Any]:
    return {
        "id": row.id,
        "entry_type": row.entry_type,
        "amount_usd": str(_usd(row.amount_usd)),
        "balance_after_usd": str(_usd(row.balance_after_usd)),
        "topup_intent_id": row.topup_intent_id,
        "gateway_request_log_id": row.gateway_request_log_id,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat(),
    }


def serialize_gateway_topup_intent(intent: GatewayTopupIntent) -> dict[str, Any]:
    return {
        "id": intent.id,
        "public_reference": intent.public_reference,
        "amount_usd": f"{Decimal(intent.amount_cents) / CENTS_PER_USD:.2f}",
        "currency": intent.currency,
        "status": intent.status,
        "created_at": intent.created_at.isoformat(),
        "completed_at": intent.completed_at.isoformat() if intent.completed_at else None,
    }


def gateway_wallet_history(db: Session, user_id: str, *, limit: int = 20) -> list[GatewayWalletLedger]:
    return (
        db.query(GatewayWalletLedger)
        .filter_by(user_id=user_id)
        .order_by(GatewayWalletLedger.created_at.desc())
        .limit(limit)
        .all()
    )


def gateway_topup_history(db: Session, user_id: str, *, limit: int = 20) -> list[GatewayTopupIntent]:
    return (
        db.query(GatewayTopupIntent)
        .filter_by(user_id=user_id)
        .order_by(GatewayTopupIntent.created_at.desc())
        .limit(limit)
        .all()
    )


def create_gateway_topup_checkout(db: Session, user: User, amount_usd: Decimal | int | float | str, *, locale: str) -> dict[str, Any]:
    cents = topup_amount_to_cents(amount_usd)
    intent = GatewayTopupIntent(
        public_reference=f"gwt_{secrets.token_urlsafe(18)}",
        user_id=user.id,
        amount_cents=cents,
        currency="USD",
        status="created",
        metadata_json={"purpose": "gateway_topup", "locale": locale},
    )
    db.add(intent)
    db.flush()
    checkout = StripeService().create_gateway_topup_session(db, user, intent, locale=locale)
    intent.status = "checkout_created"
    db.commit()
    return {**checkout, "topup": serialize_gateway_topup_intent(intent)}


def assert_gateway_wallet_available(db: Session, user_id: str) -> GatewayWallet:
    wallet = gateway_wallet(db, user_id)
    if _usd(wallet.available_balance_usd or 0) <= 0:
        raise GatewayProviderError(
            "GATEWAY_INSUFFICIENT_BALANCE",
            "Gateway wallet balance is insufficient. Add prepaid USD credit in the Gateway console.",
            status_code=402,
            retryable=False,
        )
    return wallet


def debit_gateway_wallet_for_request(
    db: Session,
    *,
    user_id: str,
    request_log: GatewayRequestLog,
    amount_usd: Decimal,
) -> GatewayWallet:
    """Atomically debit an accepted metered request without allowing overdraft.

    The balance is re-locked when usage arrives, so concurrent API calls cannot
    take it below zero. If a response costs more than the remaining amount, the
    charge is rejected and the response is not finalized as successful.
    """

    amount = _usd(amount_usd)
    if amount <= 0:
        return gateway_wallet(db, user_id)
    wallet = gateway_wallet(db, user_id, lock=True)
    existing = db.query(GatewayWalletLedger).filter_by(gateway_request_log_id=request_log.id).one_or_none()
    if existing:
        return wallet
    current = _usd(wallet.available_balance_usd or 0)
    if current < amount:
        raise GatewayProviderError(
            "GATEWAY_INSUFFICIENT_BALANCE",
            "Gateway wallet balance is insufficient for this request. Add prepaid USD credit and retry.",
            status_code=402,
            retryable=False,
        )
    balance_after = _usd(current - amount)
    wallet.available_balance_usd = balance_after
    wallet.lifetime_debited_usd = _usd(Decimal(str(wallet.lifetime_debited_usd or 0)) + amount)
    db.add(
        GatewayWalletLedger(
            wallet_id=wallet.id,
            user_id=user_id,
            entry_type="usage",
            amount_usd=-amount,
            balance_after_usd=balance_after,
            idempotency_key=f"gateway-request:{request_log.request_id}",
            gateway_request_log_id=request_log.id,
            metadata_json={"request_id": request_log.request_id, "model": request_log.public_model},
        )
    )
    return wallet


def _topup_intent_by_session(db: Session, obj: dict[str, Any]) -> GatewayTopupIntent | None:
    metadata = obj.get("metadata") or {}
    intent_id = metadata.get("gateway_topup_intent_id")
    if intent_id:
        return db.get(GatewayTopupIntent, intent_id)
    session_id = obj.get("id")
    if session_id:
        return db.query(GatewayTopupIntent).filter_by(stripe_checkout_session_id=session_id).one_or_none()
    return None


def is_gateway_topup_checkout(db: Session, obj: dict[str, Any]) -> bool:
    metadata = obj.get("metadata") or {}
    return metadata.get("purpose") == "gateway_topup" or _topup_intent_by_session(db, obj) is not None


def _mark_topup_manual_review(intent: GatewayTopupIntent | None, message: str) -> None:
    if intent:
        intent.status = "requires_manual_review"
        intent.metadata_json = {**(intent.metadata_json or {}), "manual_review_reason": message}


def settle_gateway_topup_from_checkout(db: Session, obj: dict[str, Any]) -> GatewayTopupIntent:
    """Credit a paid Checkout Session after validating its stored intent.

    The exact USD amount comes from the intent and must match Stripe's signed
    event payload. The checkout success redirect never changes a balance.
    """

    intent = _topup_intent_by_session(db, obj)
    if not intent:
        raise GatewayTopupError("GATEWAY_TOPUP_INTENT_NOT_FOUND", "Gateway top-up checkout does not match a known intent")
    metadata = obj.get("metadata") or {}
    session_id = obj.get("id")
    if metadata.get("purpose") != "gateway_topup" or metadata.get("gateway_topup_intent_id") != intent.id:
        _mark_topup_manual_review(intent, "Gateway top-up metadata does not match its intent")
        raise GatewayTopupError("GATEWAY_TOPUP_METADATA_MISMATCH", "Gateway top-up metadata does not match its intent")
    if not session_id or session_id != intent.stripe_checkout_session_id:
        _mark_topup_manual_review(intent, "Gateway top-up checkout session does not match its intent")
        raise GatewayTopupError("GATEWAY_TOPUP_SESSION_MISMATCH", "Gateway top-up checkout session does not match its intent")
    settings = get_settings()
    payment_status = obj.get("payment_status")
    if settings.billing_mode == "stripe" and payment_status != "paid":
        # Delayed payment methods emit checkout.session.async_payment_succeeded
        # once this becomes paid; no balance is credited before then.
        return intent
    amount_total = obj.get("amount_total")
    currency = str(obj.get("currency") or intent.currency).upper()
    try:
        received_cents = int(amount_total) if amount_total is not None else intent.amount_cents
    except (TypeError, ValueError) as exc:
        _mark_topup_manual_review(intent, "Gateway top-up payment amount is invalid")
        raise GatewayTopupError("GATEWAY_TOPUP_AMOUNT_MISMATCH", "Gateway top-up payment amount is invalid") from exc
    if currency != intent.currency.upper() or received_cents != intent.amount_cents:
        _mark_topup_manual_review(intent, "Gateway top-up payment amount or currency does not match its intent")
        raise GatewayTopupError("GATEWAY_TOPUP_AMOUNT_MISMATCH", "Gateway top-up payment amount or currency does not match its intent")
    user = db.get(User, intent.user_id)
    customer_id = obj.get("customer")
    if not user or not customer_id or customer_id != intent.stripe_customer_id or (user.stripe_customer_id and customer_id != user.stripe_customer_id):
        _mark_topup_manual_review(intent, "Gateway top-up customer does not match its user")
        raise GatewayTopupError("GATEWAY_TOPUP_CUSTOMER_MISMATCH", "Gateway top-up customer does not match its user")

    wallet = gateway_wallet(db, intent.user_id, lock=True)
    idempotency_key = f"stripe-checkout:{session_id}"
    existing = db.query(GatewayWalletLedger).filter_by(idempotency_key=idempotency_key).one_or_none()
    if existing is None:
        amount = _usd(Decimal(intent.amount_cents) / CENTS_PER_USD)
        balance_after = _usd(Decimal(str(wallet.available_balance_usd or 0)) + amount)
        wallet.available_balance_usd = balance_after
        wallet.lifetime_credited_usd = _usd(Decimal(str(wallet.lifetime_credited_usd or 0)) + amount)
        db.add(
            GatewayWalletLedger(
                wallet_id=wallet.id,
                user_id=intent.user_id,
                entry_type="topup",
                amount_usd=amount,
                balance_after_usd=balance_after,
                idempotency_key=idempotency_key,
                topup_intent_id=intent.id,
                metadata_json={"stripe_checkout_session_id": session_id, "stripe_payment_intent_id": obj.get("payment_intent")},
            )
        )
    intent.status = "completed"
    intent.completed_at = intent.completed_at or datetime.now(timezone.utc)
    intent.stripe_payment_intent_id = obj.get("payment_intent") or intent.stripe_payment_intent_id
    return intent


def expire_gateway_topup_from_checkout(db: Session, obj: dict[str, Any]) -> None:
    intent = _topup_intent_by_session(db, obj)
    if intent and intent.status in {"created", "checkout_created"}:
        intent.status = "expired"
