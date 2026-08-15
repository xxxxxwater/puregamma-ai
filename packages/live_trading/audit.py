"""Append-only trading audit helpers.

Every LIVE trading action is recorded on ``TradingAuditLog`` with a
``trace_id``. Callers pass the trace id down from the HTTP layer so a single
request can be traced across intent -> risk -> order -> ledger.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from packages.database.models import TradingAuditLog


def new_trace_id() -> str:
    return uuid.uuid4().hex


def audit(
    db: Session,
    *,
    user_id: str,
    action: str,
    status: str,
    trace_id: str,
    idempotency_key: str,
    actor_type: str = "system",
    strategy_id: str | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
    request_json: dict | None = None,
    result_json: dict | None = None,
    error: str | None = None,
) -> TradingAuditLog:
    existing = (
        db.query(TradingAuditLog)
        .filter_by(idempotency_key=idempotency_key)
        .one_or_none()
    )
    if existing:
        return existing
    row = TradingAuditLog(
        user_id=user_id,
        conversation_id=conversation_id,
        strategy_id=strategy_id,
        run_id=run_id,
        action=action,
        status=status,
        actor_type=actor_type,
        request_json=request_json or {},
        result_json=result_json or {},
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        error_message=error,
    )
    db.add(row)
    return row
