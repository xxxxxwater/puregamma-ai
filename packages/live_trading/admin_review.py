"""Administrator review of the LIVE control plane.

Kill switches, user LIVE eligibility and reconciliation exceptions. Callers
are the ``/admin/trading/*`` routes, which authorize with the server-side
admin role check before anything here runs; hiding a page in the browser is
not authorization.

Every state change appends a ``TradingAuditLog`` row (actor ``admin``) whose
``request_json`` names the administrator and the stated reason. Rows that are
immutable by design (reconciliations) are never edited: a review is a new
audit row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import literal
from sqlalchemy.orm import Session

from packages.database.models import (
    BrokerConnection,
    LiveUserApproval,
    TradingAuditLog,
    TradingKillSwitch,
    TradingMandate,
    TradingReconciliation,
    User,
    utcnow,
)
from packages.live_trading import kill_switch as kill_switch_service
from packages.live_trading.audit import audit, new_trace_id
from packages.live_trading.decimal_text import decimal_text
from packages.live_trading.enums import KillSwitchScope
from packages.live_trading.ledger_view import (
    RECONCILIATION_REVIEW_ACTION,
    latest_reviews,
    serialize_reconciliation,
)

KILL_SWITCH_ENGAGED = "LIVE_KILL_SWITCH_ENGAGED"
KILL_SWITCH_RELEASED = "LIVE_KILL_SWITCH_RELEASED"
LIVE_APPROVAL_SET = "LIVE_USER_APPROVAL_SET"
ADMIN_ACTIONS = (KILL_SWITCH_ENGAGED, KILL_SWITCH_RELEASED, LIVE_APPROVAL_SET, RECONCILIATION_REVIEW_ACTION)


class AdminReviewError(ValueError):
    """A request that is well-formed but not acceptable (HTTP 400)."""


class AdminForbidden(PermissionError):
    """A request this administrator may not make (HTTP 403)."""


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def _admin_audit(
    db: Session,
    *,
    admin: User,
    action: str,
    status: str,
    subject_user_id: str,
    request: dict,
    result: dict | None = None,
    trace_id: str | None = None,
    key: str | None = None,
) -> TradingAuditLog:
    return audit(
        db,
        user_id=subject_user_id,
        action=action,
        status=status,
        trace_id=trace_id or new_trace_id(),
        idempotency_key=key or f"audit:admin:{action.lower()}:{uuid.uuid4().hex}",
        actor_type="admin",
        request_json={"admin_user_id": admin.id, **request},
        result_json=result or {},
    )


# ---------------------------------------------------------------------------
# Kill switches
# ---------------------------------------------------------------------------


def serialize_kill_switch(row: TradingKillSwitch) -> dict:
    return {
        "id": row.id,
        "scope": row.scope,
        "scope_id": row.scope_id,
        "state": row.state,
        "reason": row.reason,
        "triggered_by": row.triggered_by,
        "triggered_at": _iso(row.triggered_at),
        "resolved_by": row.resolved_by,
        "resolved_at": _iso(row.resolved_at),
        "trace_id": row.trace_id,
    }


def list_kill_switches(db: Session, *, include_released: bool = True, limit: int = 50) -> dict:
    active = (
        db.query(TradingKillSwitch)
        .filter_by(state="active")
        .order_by(TradingKillSwitch.triggered_at.desc())
        .all()
    )
    released = []
    if include_released:
        released = (
            db.query(TradingKillSwitch)
            .filter(TradingKillSwitch.state != "active")
            .order_by(TradingKillSwitch.resolved_at.desc(), TradingKillSwitch.triggered_at.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )
    return {
        "active": [serialize_kill_switch(row) for row in active],
        "released": [serialize_kill_switch(row) for row in released],
    }


def _kill_switch_subject(db: Session, admin: User, scope: str, scope_id: str | None) -> tuple[str, TradingMandate | None]:
    """Validate the target and return the user the switch is about."""
    if scope == KillSwitchScope.GLOBAL.value:
        if scope_id:
            raise AdminReviewError("A global kill switch takes no scope_id")
        return admin.id, None
    if not scope_id:
        raise AdminReviewError(f"A {scope} kill switch needs a scope_id")
    if scope == KillSwitchScope.USER.value:
        target = db.query(User).filter_by(id=scope_id).one_or_none()
        if target is None:
            raise LookupError("User not found")
        return target.id, None
    if scope == KillSwitchScope.MANDATE.value:
        mandate = db.query(TradingMandate).filter_by(id=scope_id).one_or_none()
        if mandate is None:
            raise LookupError("Mandate not found")
        return mandate.user_id, mandate
    if scope == KillSwitchScope.CONNECTION.value:
        connection = db.query(BrokerConnection).filter_by(id=scope_id).one_or_none()
        if connection is None:
            raise LookupError("Broker connection not found")
        return connection.user_id, None
    raise AdminReviewError("Unknown kill switch scope")


def set_kill_switch(
    db: Session,
    admin: User,
    *,
    scope: str,
    scope_id: str | None,
    active: bool,
    reason: str,
) -> dict:
    """Engage or release one kill switch. A reason is required both ways.

    Engaging is idempotent (an already-active switch is returned). Releasing
    something that is not active is a ``LookupError`` so a typo cannot read as
    success. Orders, cancels, queries and reconciliation are unaffected by
    either direction; only new exposure is blocked while engaged.
    """
    reason = (reason or "").strip()
    if not reason:
        raise AdminReviewError("A reason is required")
    subject_user_id, mandate = _kill_switch_subject(db, admin, scope, scope_id)
    trace_id = new_trace_id()
    if active:
        row = kill_switch_service.engage(
            db, scope=scope, scope_id=scope_id, reason=reason, triggered_by="admin", trace_id=trace_id
        )
        if mandate is not None:
            mandate.kill_switch_state = "active"
            mandate.paused = True
            mandate.pause_reason = f"admin kill switch: {reason[:500]}"
        _admin_audit(
            db, admin=admin, action=KILL_SWITCH_ENGAGED, status="ACTIVE", subject_user_id=subject_user_id,
            request={"scope": scope, "scope_id": scope_id, "reason": reason}, result={"kill_switch_id": row.id},
            trace_id=trace_id,
        )
    else:
        released = kill_switch_service.release(
            db, scope=scope, scope_id=scope_id, resolved_by=admin.id, trace_id=trace_id
        )
        if not released:
            db.rollback()
            raise LookupError("No active kill switch in scope")
        if mandate is not None and mandate.kill_switch_state == "active":
            # The mandate stays paused: resuming is the owner's explicit,
            # fully re-gated action, never a side effect of a release.
            mandate.kill_switch_state = "inactive"
        _admin_audit(
            db, admin=admin, action=KILL_SWITCH_RELEASED, status="INACTIVE", subject_user_id=subject_user_id,
            request={"scope": scope, "scope_id": scope_id, "reason": reason}, trace_id=trace_id,
        )
    db.commit()
    return {"trace_id": trace_id, "active": active, "scope": scope, "scope_id": scope_id}


# ---------------------------------------------------------------------------
# User LIVE eligibility
# ---------------------------------------------------------------------------


def _serialize_approval(row: LiveUserApproval, email: str | None = None) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "email": email,
        "status": row.status,
        "max_total_notional": decimal_text(row.max_total_notional),
        "reviewed_by": row.reviewed_by,
        "reviewed_at": _iso(row.reviewed_at),
        "revoked_at": _iso(row.revoked_at),
        "notes": row.notes,
    }


def list_live_approvals(db: Session, *, limit: int = 100) -> list[dict]:
    rows = (
        db.query(LiveUserApproval, User.email)
        .join(User, User.id == LiveUserApproval.user_id)
        .order_by(LiveUserApproval.updated_at.desc(), LiveUserApproval.id.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [_serialize_approval(row, email) for row, email in rows]


def set_live_approval(
    db: Session,
    admin: User,
    *,
    user_id: str,
    approve: bool,
    max_total_notional: str,
    notes: str,
) -> dict:
    """Approve or reject one user's LIVE eligibility.

    An administrator cannot approve their own eligibility, and a reason is
    required. This does not enable LIVE: the deployment gates
    (``LIVE_TRADING_ENABLED`` and friends) are evaluated independently on
    every order.
    """
    notes = (notes or "").strip()
    if not notes:
        raise AdminReviewError("A reason is required")
    target = db.query(User).filter_by(id=user_id).one_or_none()
    if target is None:
        raise LookupError("User not found")
    if approve and target.id == admin.id:
        raise AdminForbidden("An administrator cannot approve their own LIVE eligibility")
    try:
        cap = Decimal(str(max_total_notional))
    except (InvalidOperation, ValueError) as exc:
        raise AdminReviewError("max_total_notional must be a decimal string") from exc
    if not cap.is_finite() or cap < 0:
        raise AdminReviewError("max_total_notional must be a non-negative decimal")
    row = db.query(LiveUserApproval).filter_by(user_id=user_id).one_or_none()
    previous = row.status if row else "none"
    if row is None:
        row = LiveUserApproval(user_id=user_id)
        db.add(row)
    row.status = "approved" if approve else "rejected"
    row.max_total_notional = cap
    row.reviewed_by = admin.id
    row.reviewed_at = utcnow()
    row.notes = notes
    row.revoked_at = None if approve else utcnow()
    db.flush()
    _admin_audit(
        db, admin=admin, action=LIVE_APPROVAL_SET, status=row.status.upper(), subject_user_id=user_id,
        request={"approve": approve, "max_total_notional": decimal_text(cap), "reason": notes},
        result={"approval_id": row.id, "previous_status": previous},
    )
    db.commit()
    db.refresh(row)
    return _serialize_approval(row, target.email)


# ---------------------------------------------------------------------------
# Reconciliation exceptions
# ---------------------------------------------------------------------------


def list_reconciliations(
    db: Session,
    *,
    status: str | None = None,
    exceptions_only: bool = False,
    unreviewed_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    query = db.query(TradingReconciliation)
    if status:
        query = query.filter(TradingReconciliation.status == status)
    elif exceptions_only:
        query = query.filter(TradingReconciliation.status != "ok")
    if unreviewed_only:
        # In SQL, before the LIMIT: filtering the newest N afterwards hid
        # every older unreviewed exception behind reviewed ones.
        reviewed = (
            db.query(TradingAuditLog.id)
            .filter(
                TradingAuditLog.action == RECONCILIATION_REVIEW_ACTION,
                TradingAuditLog.idempotency_key.like(literal("audit:recon-review:") + TradingReconciliation.id + literal(":%")),
            )
            .exists()
        )
        query = query.filter(~reviewed)
    rows = (
        query.order_by(TradingReconciliation.created_at.desc(), TradingReconciliation.id.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    reviews = latest_reviews(db, [row.id for row in rows])
    items = []
    for row in rows:
        if unreviewed_only and row.id in reviews:
            continue
        item = serialize_reconciliation(row, reviews.get(row.id), include_reviewer=True)
        item["user_id"] = row.user_id
        item["trace_id"] = row.trace_id
        items.append(item)
    return items


def review_reconciliation(db: Session, admin: User, reconciliation_id: str, *, note: str) -> dict:
    """Mark a reconciliation as reviewed with a note.

    Appends an audit row; the reconciliation itself is immutable and the
    paused mandate stays paused (resolving it is a separate, explicit act).
    """
    note = (note or "").strip()
    if not note:
        raise AdminReviewError("A review note is required")
    row = db.query(TradingReconciliation).filter_by(id=reconciliation_id).one_or_none()
    if row is None:
        raise LookupError("Reconciliation not found")
    _admin_audit(
        db, admin=admin, action=RECONCILIATION_REVIEW_ACTION, status="REVIEWED", subject_user_id=row.user_id,
        request={"reconciliation_id": row.id, "note": note},
        result={"reconciliation_status": row.status},
        trace_id=row.trace_id,
        key=f"audit:recon-review:{row.id}:{uuid.uuid4().hex}",
    )
    db.commit()
    reviews = latest_reviews(db, [row.id])
    item = serialize_reconciliation(row, reviews.get(row.id), include_reviewer=True)
    item["user_id"] = row.user_id
    return item


# ---------------------------------------------------------------------------
# Audit trail of administrator actions
# ---------------------------------------------------------------------------


def list_admin_audit(db: Session, *, limit: int = 50) -> list[dict]:
    rows = (
        db.query(TradingAuditLog)
        .filter(TradingAuditLog.actor_type == "admin", TradingAuditLog.action.in_(ADMIN_ACTIONS))
        .order_by(TradingAuditLog.created_at.desc(), TradingAuditLog.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "status": row.status,
            "user_id": row.user_id,
            "admin_user_id": (row.request_json or {}).get("admin_user_id"),
            "request": row.request_json or {},
            "result": row.result_json or {},
            "trace_id": row.trace_id,
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]
