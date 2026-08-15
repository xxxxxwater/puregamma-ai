"""Kill switch service (global | user | mandate | connection scopes).

Triggering is immediate and additive: switches are INSERT-only rows whose
state only changes through an explicit admin release. The control plane
queries these before any order submission.

After a kill switch is engaged:
- new orders are refused (control plane gate)
- queries, cancels, fill recording, and reconciliation keep working
- recovery always requires a human (admin) release action
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from packages.database.models import TradingKillSwitch, TradingMandate, utcnow
from packages.live_trading.enums import KillSwitchScope


class KillSwitchError(RuntimeError):
    pass


def _active(db: Session, scope: str, scope_id: str | None = None) -> TradingKillSwitch | None:
    query = db.query(TradingKillSwitch).filter_by(scope=scope, state="active")
    if scope_id is None:
        query = query.filter(TradingKillSwitch.scope_id.is_(None))
    else:
        query = query.filter_by(scope_id=scope_id)
    return query.order_by(TradingKillSwitch.triggered_at.desc()).first()


def is_engaged(db: Session, scope: str, scope_id: str | None = None) -> bool:
    return _active(db, scope, scope_id) is not None


def engage(
    db: Session,
    *,
    scope: KillSwitchScope | str,
    scope_id: str | None = None,
    reason: str,
    triggered_by: str = "admin",
    trace_id: str | None = None,
) -> TradingKillSwitch:
    scope_value = str(scope)
    if _active(db, scope_value, scope_id):
        existing = _active(db, scope_value, scope_id)
        assert existing is not None
        return existing
    row = TradingKillSwitch(
        scope=scope_value,
        scope_id=scope_id,
        state="active",
        reason=reason[:2000],
        triggered_by=triggered_by,
        triggered_at=utcnow(),
        trace_id=trace_id,
    )
    db.add(row)
    db.flush()
    return row


def release(
    db: Session,
    *,
    scope: KillSwitchScope | str,
    scope_id: str | None = None,
    resolved_by: str,
    trace_id: str | None = None,
) -> bool:
    """Admin-only recovery. Marks every active switch in scope as inactive."""
    rows = (
        db.query(TradingKillSwitch)
        .filter_by(scope=str(scope), state="active")
        .all()
    )
    for row in rows:
        if row.scope_id != scope_id:
            continue
        row.state = "inactive"
        row.resolved_by = resolved_by
        row.resolved_at = utcnow()
    db.flush()
    return len(rows) > 0


def mandate_trade_allowed(db: Session, mandate: TradingMandate) -> tuple[bool, str]:
    """Combined kill-switch check for one mandate. Returns (allowed, reason)."""
    if is_engaged(db, "global"):
        return False, "GLOBAL_KILL_SWITCH"
    if is_engaged(db, "user", mandate.user_id):
        return False, "USER_KILL_SWITCH"
    if is_engaged(db, "mandate", mandate.id):
        return False, "MANDATE_KILL_SWITCH"
    if mandate.kill_switch_state == "active":
        return False, "MANDATE_KILL_SWITCH_STATE"
    if mandate.paused:
        return False, "MANDATE_PAUSED"
    if mandate.broker_connection_id and is_engaged(
        db, "connection", mandate.broker_connection_id
    ):
        return False, "CONNECTION_KILL_SWITCH"
    return True, ""


def active_switches(db: Session, user_id: str) -> list[dict]:
    rows = (
        db.query(TradingKillSwitch)
        .filter_by(state="active")
        .order_by(TradingKillSwitch.triggered_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "scope": row.scope,
            "scope_id": row.scope_id,
            "reason": row.reason,
            "triggered_by": row.triggered_by,
            "triggered_at": row.triggered_at.isoformat() if row.triggered_at else None,
        }
        for row in rows
        if row.scope in {"global", "connection"}
        or (row.scope == "user" and row.scope_id == user_id)
        or row.scope == "mandate"
    ]
