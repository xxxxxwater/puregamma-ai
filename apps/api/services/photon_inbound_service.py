from __future__ import annotations

"""Persistent, retryable processing for Photon inbound iMessage events.

Pipeline:

    Photon webhook -> verify/dedup -> persist PhotonInboundTask -> Celery
    -> worker: claim row -> shared agent flow (_process_inbound)
    -> PhotonIMessageProvider.send_message() -> audit NotificationDelivery

Idempotency: the Photon message.id is the unique key. Duplicate webhooks
can never run the agent twice, double-bill, or double-send the reply.
Outbound replies use idempotency key "photon-inbound-reply:{message_id}"
and a direct NotificationDelivery row -- the user-notification billing
path is deliberately NOT used (the agent run already billed; a reply is
not an extra notification charge).

Nothing here logs bearer tokens, message bodies, phone numbers or media.
last_error stores safe error codes only.
"""

import logging
from datetime import timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from packages.database.models import NotificationDelivery, PhotonInboundTask, utcnow
from packages.database.session import SessionLocal
from packages.notifications.imessage.photon_provider import PhotonIMessageProvider


logger = logging.getLogger("puregamma.photon_inbound")

TERMINAL_STATUSES = {"sent", "no_reply", "failed_permanent"}
# Statuses from the shared inbound flow whose "reply" text must be sent back.
REPLY_STATUSES = {"completed", "duplicate", "subscription_required", "failed"}
MAX_ATTEMPTS = 3
RETRY_DELAYS_MINUTES = (1, 5, 30)
STALE_PROCESSING_MINUTES = 10
REPLY_IDEMPOTENCY_PREFIX = "photon-inbound-reply:"


def _aware(value):
    """SQLite returns naive datetimes; normalize before Python comparisons."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _dispatch(task_id: str, countdown: int | None = None) -> None:
    """Publish the task to Celery. Kept as a seam so tests can record enqueues."""
    from packages.workers.tasks import process_photon_inbound_task

    if countdown:
        process_photon_inbound_task.apply_async(args=[task_id], countdown=countdown)
    else:
        process_photon_inbound_task.apply_async(args=[task_id])


# ---------------------------------------------------------------------------
# Webhook entry
# ---------------------------------------------------------------------------


def enqueue_photon_inbound(
    db: Session,
    *,
    message_id: str,
    sender: str,
    content: str,
) -> dict:
    """Idempotent persist + enqueue. One indexed SELECT + one INSERT, so the
    webhook can acknowledge Photon within milliseconds."""
    now = utcnow()
    existing = (
        db.query(PhotonInboundTask)
        .filter(PhotonInboundTask.message_id == message_id)
        .one_or_none()
    )
    if existing is not None:
        if existing.status in TERMINAL_STATUSES:
            return {"status": "duplicate", "reason": f"terminal:{existing.status}"}
        if existing.status in {"pending", "processing"}:
            return {"status": "duplicate", "reason": "already_queued"}
        if existing.status == "failed_retryable" and _aware(existing.next_retry_at) is not None and _aware(existing.next_retry_at) > now:
            return {"status": "duplicate", "reason": "retry_pending"}
        # failed_retryable and due: fall through and re-enqueue.
        task = existing
    else:
        task = PhotonInboundTask(message_id=message_id, sender=sender, content=content)
        db.add(task)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent duplicate webhook: the winning insert enqueues.
            db.rollback()
            return {"status": "duplicate", "reason": "race"}
    _dispatch(task.id)
    return {"status": "queued", "task_id": task.id}


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def _claim(db: Session, task_id: str) -> PhotonInboundTask | None:
    query = db.query(PhotonInboundTask).filter(PhotonInboundTask.id == task_id)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    task = query.one_or_none()
    if task is None or task.status in TERMINAL_STATUSES:
        return None
    last_attempt = _aware(task.last_attempt_at)
    if (
        task.status == "processing"
        and last_attempt is not None
        and (utcnow() - last_attempt) < timedelta(minutes=STALE_PROCESSING_MINUTES)
    ):
        # Another worker holds this row (or it is a fresh duplicate enqueue).
        return None
    task.status = "processing"
    task.attempt_count = (task.attempt_count or 0) + 1
    task.last_attempt_at = utcnow()
    task.next_retry_at = None
    db.commit()
    return task


def process_photon_inbound(task_id: str, db: Session | None = None) -> dict:
    """Run one processing attempt for a persisted Photon inbound event.

    Reuses the shared inbound business flow (user matching, verification
    status, agent, billing, limits) via _process_inbound, then sends the
    reply through PhotonIMessageProvider. A db session may be injected for
    tests; the production worker uses SessionLocal.
    """
    own_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        task = _claim(db, task_id)
        if task is None:
            return {"status": "skipped", "reason": "not_claimable", "task_id": task_id}
        from apps.api.config import get_settings

        if get_settings().imessage_provider != "photon":
            # The operator switched back to macos_relay/disabled: never send
            # through Photon while it is not the selected provider. Pending
            # rows are archived without retries (re-enabling photon later does
            # not resurrect replies from the disabled window).
            return _finish(db, task, "failed_permanent", "photon_provider_disabled")
        # Lazy imports avoid a service <-> router import cycle.
        from apps.api.routers.imessage_agent import InboundMessage, _process_inbound, resolve_verified_user

        payload = InboundMessage(message_id=task.message_id, sender=task.sender, content=task.content)
        try:
            result = _process_inbound(db, payload)
        except Exception as exc:  # unexpected agent/infra failure; safe code only
            db.rollback()
            return _mark_failure(db, task, exc.__class__.__name__)
        reply = str(result.get("reply") or "") if result.get("status") in REPLY_STATUSES else ""
        if not reply.strip():
            # Unverified sender or an intentionally empty reply: nothing to send.
            return _finish(db, task, "no_reply", None)
        resolved = resolve_verified_user(db, task.sender)
        if not resolved:
            # Defensive: never send to an unverified recipient.
            return _finish(db, task, "no_reply", "unverified")
        sender, preference, user = resolved
        outcome = _send_reply(db, task, user.id, sender, reply, getattr(preference, "locale", None) or "en")
        if outcome == "sent":
            return _finish(db, task, "sent", None)
        if outcome == "failed_permanent":
            return _finish(db, task, "failed_permanent", "photon_reply_permanent")
        return _mark_failure(db, task, "photon_reply_failed")
    finally:
        if own_session:
            db.close()


def _send_reply(
    db: Session,
    task: PhotonInboundTask,
    user_id: str,
    recipient: str,
    reply: str,
    locale: str,
) -> str:
    """Send the reply via PhotonIMessageProvider and persist an auditable
    NotificationDelivery row. Returns sent | failed_retryable |
    failed_permanent. The dispatcher billing path is intentionally NOT used.
    """
    idempotency_key = f"{REPLY_IDEMPOTENCY_PREFIX}{task.message_id}"
    existing = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.idempotency_key == idempotency_key)
        .one_or_none()
    )
    if existing is not None and existing.status == "sent":
        task.outbound_delivery_id = existing.id
        db.commit()
        return "sent"
    provider = PhotonIMessageProvider()
    result = provider.send_message(recipient, reply, idempotency_key)
    if result.ok:
        status = "sent"
    elif result.response.get("status") == "invalid_recipient":
        status = "failed_permanent"
    else:
        status = "failed_retryable"
    if existing is None:
        delivery = NotificationDelivery(
            user_id=user_id,
            channel="imessage",
            recipient=recipient,
            payload={"type": "photon_inbound_reply", "message": reply},
            locale=locale,
            status=status,
            provider_response=result.response,
            idempotency_key=idempotency_key,
            attempt_count=1,
            last_attempt_at=utcnow(),
            next_retry_at=None if result.ok else utcnow() + timedelta(minutes=1),
            last_error=None if result.ok else "provider_failed",
            sent_at=utcnow() if result.ok else None,
        )
        db.add(delivery)
        db.flush()
    else:
        existing.status = status
        existing.provider_response = result.response
        existing.attempt_count = (existing.attempt_count or 0) + 1
        existing.last_attempt_at = utcnow()
        existing.next_retry_at = None if result.ok else utcnow() + timedelta(minutes=1)
        existing.last_error = None if result.ok else "provider_failed"
        existing.sent_at = utcnow() if result.ok else existing.sent_at
        delivery = existing
    task.outbound_delivery_id = delivery.id
    db.commit()
    return status


def _finish(db: Session, task: PhotonInboundTask, status: str, last_error: str | None) -> dict:
    task.status = status
    task.last_error = last_error
    task.next_retry_at = None
    db.commit()
    return {"status": status, "task_id": task.id}


def _mark_failure(db: Session, task: PhotonInboundTask, error_code: str) -> dict:
    """Record a safe failure and schedule a bounded retry."""
    if (task.attempt_count or 0) >= MAX_ATTEMPTS:
        task.status = "failed_permanent"
        task.next_retry_at = None
        status = "failed_permanent"
    else:
        task.status = "failed_retryable"
        delay_minutes = RETRY_DELAYS_MINUTES[min(max(task.attempt_count - 1, 0), 2)]
        task.next_retry_at = utcnow() + timedelta(minutes=delay_minutes)
        status = "failed_retryable"
    task.last_error = error_code
    db.commit()
    if status == "failed_retryable":
        _dispatch(task.id, countdown=60 * delay_minutes)
    logger.warning(
        "photon_inbound_failed provider=photon message_id=%s status=%s error=%s",
        task.message_id,
        status,
        error_code,
    )
    return {"status": status, "error": error_code}


def reap_photon_inbound_tasks(limit: int = 50, db: Session | None = None) -> dict:
    """Re-enqueue tasks a crashed worker left in "processing", and
    "failed_retryable" rows whose scheduled retry was missed (broker loss /
    scheduler restart). Bounded by MAX_ATTEMPTS inside process_photon_inbound.
    """
    own_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        stale_since = utcnow() - timedelta(minutes=STALE_PROCESSING_MINUTES)
        rows = (
            db.query(PhotonInboundTask)
            .filter(
                or_(
                    and_(
                        PhotonInboundTask.status == "processing",
                        PhotonInboundTask.last_attempt_at < stale_since,
                    ),
                    and_(
                        PhotonInboundTask.status == "failed_retryable",
                        PhotonInboundTask.next_retry_at <= utcnow(),
                    ),
                )
            )
            .order_by(PhotonInboundTask.updated_at)
            .limit(limit)
            .all()
        )
        for task in rows:
            _dispatch(task.id)
        return {"enqueued": len(rows)}
    finally:
        if own_session:
            db.close()
