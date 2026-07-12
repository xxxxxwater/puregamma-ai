from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_db
from apps.api.services.billing_service import parse_event_payload, process_stripe_event


router = APIRouter(tags=["stripe"])
logger = logging.getLogger(__name__)


def validate_stripe_signature_timestamp(stripe_signature: str | None, tolerance_seconds: int) -> None:
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature: missing Stripe-Signature")
    timestamp = None
    for part in stripe_signature.split(","):
        key, _, value = part.partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid Stripe signature: invalid timestamp") from exc
            break
    if timestamp is None:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature: missing timestamp")
    if abs(int(time.time()) - timestamp) > tolerance_seconds:
        raise HTTPException(status_code=400, detail="Expired Stripe-Signature timestamp")


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    payload = await request.body()
    started = time.perf_counter()
    event_id = None
    event_type = None
    try:
        if settings.billing_mode == "stripe":
            if not settings.stripe_webhook_secret:
                raise HTTPException(status_code=503, detail="Stripe webhook is not configured")
            validate_stripe_signature_timestamp(stripe_signature, settings.stripe_webhook_tolerance_seconds)
            try:
                import stripe
            except ImportError as exc:
                raise HTTPException(status_code=500, detail="stripe package is required") from exc
            try:
                try:
                    event = stripe.Webhook.construct_event(payload, stripe_signature, settings.stripe_webhook_secret, tolerance=settings.stripe_webhook_tolerance_seconds)
                except TypeError:
                    event = stripe.Webhook.construct_event(payload, stripe_signature, settings.stripe_webhook_secret)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid Stripe signature: {exc}") from exc
        else:
            event = parse_event_payload(payload)
        event_dict = dict(event)
        event_id = event_dict.get("id")
        event_type = event_dict.get("type")
        return process_stripe_event(db, event_dict, payload)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info("stripe_webhook event_id=%s event_type=%s elapsed_ms=%s", event_id, event_type, elapsed_ms)
