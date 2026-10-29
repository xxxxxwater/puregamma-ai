"""Order-state sync results and the user's "re-check" request.

An order whose venue state is UNKNOWN is resolved by QUERYING the venue, never
by submitting again. This module records what each query said and lets the
owner ask for one more query:

- results are appended to ``TradingAuditLog`` (action ``LIVE_ORDER_SYNC``,
  key ``audit:sync:<order id>:<nonce>``); the background task only appends
  when the answer changed, a user re-check always appends;
- a re-check request is its own audit row (``LIVE_ORDER_RECHECK_REQUESTED``,
  key ``audit:recheck:<order id>:<nonce>``), which is also the rate-limit
  clock: one request per order per ``LIVE_ORDER_RECHECK_MIN_INTERVAL_SECONDS``;
- no schema change: everything lives in existing audit rows and
  ``live_orders.last_sync_at``.

The re-check path calls ``control_plane.sync_order_status`` and nothing else;
it never touches ``submit_order``/``cancel_order``. It is allowed while a kill
switch is engaged (kill switches block new exposure, not queries).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import LiveOrder, TradingAuditLog, utcnow
from packages.live_trading import audit as audit_service
from packages.live_trading.enums import TERMINAL_ORDER_STATUSES

SYNC_ACTION = "LIVE_ORDER_SYNC"
RECHECK_ACTION = "LIVE_ORDER_RECHECK_REQUESTED"
OUTCOME_RESOLVED = "resolved"  # the venue answered with a definite state
OUTCOME_STILL_UNKNOWN = "still_unknown"  # the venue answered but not definitively
OUTCOME_FAILED = "query_failed"  # the query itself failed (transport/credentials/...)
_TERMINAL = {status.value for status in TERMINAL_ORDER_STATUSES}
_HISTORY = 10


class RecheckDisabled(RuntimeError):
    pass


class RecheckNotApplicable(RuntimeError):
    pass


class RecheckRateLimited(RuntimeError):
    def __init__(self, retry_after_seconds: int, next_allowed_at: datetime):
        super().__init__(f"Re-check allowed again in {retry_after_seconds}s")
        self.retry_after_seconds = retry_after_seconds
        self.next_allowed_at = next_allowed_at


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None


def _rows(db: Session, order: LiveOrder, prefix: str, action: str, limit: int) -> list[TradingAuditLog]:
    return (
        db.query(TradingAuditLog)
        .filter(
            TradingAuditLog.user_id == order.user_id,
            TradingAuditLog.action == action,
            TradingAuditLog.idempotency_key.like(f"{prefix}:{order.id}:%"),
        )
        .order_by(TradingAuditLog.created_at.desc(), TradingAuditLog.id.desc())
        .limit(limit)
        .all()
    )


def record_sync_result(
    db: Session,
    order: LiveOrder,
    *,
    outcome: str,
    state_before: str,
    state_after: str,
    reason: str | None,
    trigger: str,
) -> TradingAuditLog | None:
    """Append one sync result. Background syncs that repeat the last answer
    are not re-recorded (``last_sync_at`` already says when it was asked)."""
    reason = (reason or None) and str(reason)[:300]
    if trigger == "background":
        latest = _rows(db, order, "audit:sync", SYNC_ACTION, 1)
        if latest:
            last = latest[0].result_json or {}
            if (last.get("outcome"), last.get("state_after"), last.get("reason")) == (outcome, state_after, reason):
                return None
    return audit_service.audit(
        db,
        user_id=order.user_id,
        action=SYNC_ACTION,
        status=outcome.upper(),
        trace_id=order.trace_id,
        idempotency_key=f"audit:sync:{order.id}:{uuid.uuid4().hex}",
        actor_type="user" if trigger == "user_recheck" else "system",
        request_json={"order_id": order.id, "trigger": trigger},
        result_json={
            "order_id": order.id,
            "outcome": outcome,
            "state_before": state_before,
            "state_after": state_after,
            "reason": reason,
        },
        error=reason if outcome == OUTCOME_FAILED else None,
    )


def _serialize_sync(row: TradingAuditLog) -> dict:
    result = row.result_json or {}
    return {
        "at": _iso(row.created_at),
        "trigger": (row.request_json or {}).get("trigger"),
        "outcome": result.get("outcome"),
        "state_before": result.get("state_before"),
        "state_after": result.get("state_after"),
        "reason": result.get("reason"),
    }


def _owned_order(db: Session, user_id: str, order_id: str, *, lock: bool = False) -> LiveOrder:
    query = db.query(LiveOrder).filter(LiveOrder.id == order_id, LiveOrder.user_id == user_id)
    if lock:
        query = query.with_for_update()
    row = query.one_or_none()
    if row is None:
        raise LookupError("Order not found")
    return row


def _recheck_window(db: Session, order: LiveOrder, now: datetime) -> datetime | None:
    """When the next re-check is allowed, or ``None`` if it is allowed now."""
    interval = timedelta(seconds=get_settings().live_order_recheck_min_interval_seconds)
    latest = _rows(db, order, "audit:recheck", RECHECK_ACTION, 1)
    if not latest:
        return None
    next_at = _aware(latest[0].created_at) + interval
    return next_at if next_at > now else None


def sync_status(db: Session, user_id: str, order_id: str) -> dict:
    order = _owned_order(db, user_id, order_id)
    settings = get_settings()
    history = [_serialize_sync(row) for row in _rows(db, order, "audit:sync", SYNC_ACTION, _HISTORY)]
    terminal = order.status in _TERMINAL
    next_at = _recheck_window(db, order, datetime.now(timezone.utc))
    if not settings.live_order_recheck_enabled:
        blocked = "disabled"
    elif terminal:
        blocked = "terminal"
    elif next_at is not None:
        blocked = "rate_limited"
    else:
        blocked = None
    return {
        "order_id": order.id,
        "status": order.status,
        "error_code": order.error_code,
        # When the server last asked the venue (or touched the order state).
        "last_sync_at": _iso(order.last_sync_at),
        "latest": history[0] if history else None,
        "history": history,
        "recheck": {
            "enabled": settings.live_order_recheck_enabled,
            "allowed": blocked is None,
            "blocked_reason": blocked,
            "min_interval_seconds": settings.live_order_recheck_min_interval_seconds,
            "next_allowed_at": _iso(next_at),
        },
    }


def request_recheck(db: Session, user_id: str, order_id: str, *, gateway=None) -> dict:
    """Ask the venue once more about one of the caller's open orders.

    Query only. Ownership is checked before anything else (another user's id
    is ``LookupError``); the rate-limit claim is committed under the order row
    lock before the venue is asked, so concurrent requests cannot both pass.
    """
    from packages.live_trading import control_plane

    if not get_settings().live_order_recheck_enabled:
        raise RecheckDisabled("Order re-check is not enabled on this deployment")
    order = _owned_order(db, user_id, order_id, lock=True)
    if order.status in _TERMINAL:
        db.rollback()
        raise RecheckNotApplicable("The order is final; there is nothing to re-check")
    now = datetime.now(timezone.utc)
    next_at = _recheck_window(db, order, now)
    if next_at is not None:
        db.rollback()
        raise RecheckRateLimited(max(1, int((next_at - now).total_seconds()) + 1), next_at)
    audit_service.audit(
        db,
        user_id=user_id,
        action=RECHECK_ACTION,
        status="REQUESTED",
        trace_id=order.trace_id,
        idempotency_key=f"audit:recheck:{order.id}:{uuid.uuid4().hex}",
        actor_type="user",
        request_json={"order_id": order.id, "status_before": order.status},
        result_json={"requested_at": utcnow().isoformat()},
    )
    db.commit()
    control_plane.sync_order_status(db, order, gateway=gateway, trigger="user_recheck")
    return sync_status(db, user_id, order_id)
