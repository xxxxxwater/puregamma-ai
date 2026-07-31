from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import (
    CreditLedger,
    CreditRefundEvent,
    CreditReservationRecord,
    CreditSettlementRecord,
    User,
)
from packages.billing.metering import CreditQuote, CreditReservation, CreditSettlement, quote_credits


class InsufficientCreditsError(RuntimeError):
    pass


def _ledger(db: Session, user: User, action: str, delta: int, metadata: dict | None = None, idempotency_key: str | None = None) -> CreditLedger:
    entry = CreditLedger(
        user_id=user.id,
        action=action,
        credits_delta=delta,
        balance_after=user.credit_balance,
        metadata_json=metadata or {},
        idempotency_key=idempotency_key,
    )
    db.add(entry)
    db.flush()
    return entry


def consume_credits(db: Session, user_id: str, action: str, amount: int, metadata: dict | None = None, idempotency_key: str | None = None) -> CreditLedger:
    if amount < 0:
        raise ValueError("Credit amount must be non-negative")
    if idempotency_key:
        existing = db.query(CreditLedger).filter_by(idempotency_key=idempotency_key).one_or_none()
        if existing:
            return existing
    user = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if not user:
        raise ValueError(f"User not found: {user_id}")
    # Re-check after the account lock. This closes the race where two requests
    # passed the optimistic lookup before either transaction committed.
    if idempotency_key:
        existing = db.query(CreditLedger).filter_by(idempotency_key=idempotency_key).one_or_none()
        if existing:
            return existing
    if not get_settings().credit_usage_enforced:
        return _ledger(db, user, action, 0, {**(metadata or {}), "credits_bypassed": amount}, idempotency_key)
    if user.credit_balance < amount:
        raise InsufficientCreditsError(
            f"Insufficient credits: required {amount}, available {user.credit_balance}"
        )
    user.credit_balance -= amount
    return _ledger(db, user, action, -amount, metadata, idempotency_key)


def refund_credits(db: Session, user_id: str, action: str, amount: int, metadata: dict | None = None, idempotency_key: str | None = None) -> CreditLedger:
    if amount < 0:
        raise ValueError("Credit amount must be non-negative")
    if idempotency_key:
        existing = db.query(CreditLedger).filter_by(idempotency_key=idempotency_key).one_or_none()
        if existing:
            return existing
    user = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if not user:
        raise ValueError(f"User not found: {user_id}")
    if idempotency_key:
        existing = db.query(CreditLedger).filter_by(idempotency_key=idempotency_key).one_or_none()
        if existing:
            return existing
    if not get_settings().credit_usage_enforced:
        return _ledger(db, user, f"{action}_refund", 0, {**(metadata or {}), "credits_bypassed": amount}, idempotency_key)
    user.credit_balance += amount
    return _ledger(db, user, f"{action}_refund", amount, metadata, idempotency_key)


def grant_credits(db: Session, user_id: str, action: str, amount: int, metadata: dict | None = None, idempotency_key: str | None = None) -> CreditLedger:
    if amount < 0:
        raise ValueError("Credit amount must be non-negative")
    if idempotency_key:
        existing = db.query(CreditLedger).filter_by(idempotency_key=idempotency_key).one_or_none()
        if existing:
            return existing
    user = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if not user:
        raise ValueError(f"User not found: {user_id}")
    if idempotency_key:
        existing = db.query(CreditLedger).filter_by(idempotency_key=idempotency_key).one_or_none()
        if existing:
            return existing
    user.credit_balance += amount
    return _ledger(db, user, action, amount, metadata, idempotency_key)


def quote_task(**kwargs) -> CreditQuote:
    """Estimate any billable task; callers must not maintain their own price math."""
    return quote_credits(**kwargs)


def _reusable_reservation(
    db: Session,
    user_id: str,
    idempotency_key: str,
) -> tuple[CreditReservationRecord | None, str]:
    """Find the live reservation for an idempotency key, or derive a fresh key.

    A reservation in a terminal state (SETTLED/REFUNDED/EXPIRED) must never be
    reused for a new operation: settling it would no-op to zero credits and the
    caller's work would go unbilled. In that case a deterministic retry key is
    derived from the terminal record so the new attempt is billed normally.
    """
    key = idempotency_key
    while True:
        record = (
            db.query(CreditReservationRecord)
            .filter_by(user_id=user_id, idempotency_key=key)
            .one_or_none()
        )
        if record is None or record.status == "RESERVED":
            return record, key
        key = f"{idempotency_key}:retry:{record.id}"


def reserve_task(
    db: Session,
    user_id: str,
    quote: CreditQuote,
    idempotency_key: str,
    metadata: dict | None = None,
) -> CreditReservation:
    existing, key = _reusable_reservation(db, user_id, idempotency_key)
    if existing:
        return CreditReservation(
            idempotency_key=existing.idempotency_key,
            credits=existing.reserved_credits,
        )

    # Serialize all mutations for the account, then repeat the idempotency
    # lookup. Without this second lookup two concurrent requests can both pass
    # the optimistic check and collide while creating the reservation row.
    db.query(User).filter(User.id == user_id).with_for_update().one()
    existing, key = _reusable_reservation(db, user_id, idempotency_key)
    if existing:
        return CreditReservation(
            idempotency_key=existing.idempotency_key,
            credits=existing.reserved_credits,
        )

    automation_key = (metadata or {}).get("automation_key")
    if automation_key:
        from packages.billing.budgets import assert_automation_budget

        assert_automation_budget(db, user_id, str(automation_key), quote.credits)

    entry = consume_credits(
        db,
        user_id,
        quote.task_type,
        quote.credits,
        {**(metadata or {}), "phase": "reservation", "quote": quote.__dict__},
        idempotency_key=key,
    )
    reserved = abs(entry.credits_delta)
    record = CreditReservationRecord(
        user_id=user_id,
        idempotency_key=key,
        task_type=quote.task_type,
        status="RESERVED",
        reserved_credits=reserved,
        quote_json=quote.__dict__,
        metadata_json=metadata or {},
        ledger_entry_id=entry.id,
    )
    db.add(record)
    db.flush()
    return CreditReservation(idempotency_key=key, credits=reserved)


def reconcile_credit_account(db: Session, user_id: str) -> dict:
    """Reconcile the mutable account cache against its append-only ledger.

    Existing accounts predate the ledger, so the opening balance is derived
    from the first entry. Every subsequent mutation can then be replayed.
    """
    entries = (
        db.query(CreditLedger)
        .filter_by(user_id=user_id)
        .order_by(CreditLedger.created_at.asc(), CreditLedger.id.asc())
        .all()
    )
    user = db.query(User).filter_by(id=user_id).one()
    if not entries:
        return {
            "user_id": user_id,
            "ledger_entries": 0,
            "opening_balance": user.credit_balance,
            "ledger_balance": user.credit_balance,
            "account_balance": user.credit_balance,
            "matches": True,
        }
    opening_balance = entries[0].balance_after - entries[0].credits_delta
    ledger_balance = opening_balance + sum(entry.credits_delta for entry in entries)
    chain_valid = all(
        entry.balance_after
        == opening_balance + sum(item.credits_delta for item in entries[: index + 1])
        for index, entry in enumerate(entries)
    )
    return {
        "user_id": user_id,
        "ledger_entries": len(entries),
        "opening_balance": opening_balance,
        "ledger_balance": ledger_balance,
        "account_balance": user.credit_balance,
        "matches": chain_valid and ledger_balance == user.credit_balance,
    }


def settle_task(
    db: Session,
    user_id: str,
    reservation: CreditReservation,
    actual: int,
    metadata: dict | None = None,
) -> CreditSettlement:
    """Settle a server-created reservation exactly once.

    The settlement idempotency key is derived from the persisted reservation;
    callers cannot choose a new key to repeat a refund.
    """
    row = (
        db.query(CreditReservationRecord)
        .filter_by(user_id=user_id, idempotency_key=reservation.idempotency_key)
        .with_for_update()
        .one_or_none()
    )
    if not row:
        raise ValueError("Credit reservation not found")
    existing = (
        db.query(CreditSettlementRecord)
        .filter_by(reservation_id=row.id)
        .one_or_none()
    )
    if existing:
        return CreditSettlement(
            reserved=row.reserved_credits,
            actual=existing.settled_credits,
            adjustment=existing.adjustment,
        )
    if row.status == "REFUNDED":
        return CreditSettlement(
            reserved=row.reserved_credits,
            actual=0,
            adjustment=row.reserved_credits,
        )
    if row.status != "RESERVED":
        raise ValueError(f"Credit reservation is already terminal: {row.status}")

    requested_actual = max(0, int(actual))
    settled_actual = requested_actual
    adjustment = row.reserved_credits - settled_actual
    settlement_status = "SETTLED"
    settlement_key = f"credit-settlement:{row.idempotency_key}"

    if adjustment > 0:
        refund_credits(
            db,
            user_id,
            "credit_settlement",
            adjustment,
            {**(metadata or {}), "phase": "settlement", "reservation_id": row.id},
            idempotency_key=f"{settlement_key}:refund",
        )
    elif adjustment < 0:
        extra = -adjustment
        account = db.query(User).filter(User.id == user_id).with_for_update().one()
        if get_settings().credit_usage_enforced and account.credit_balance < extra:
            # Never turn a completed provider call into a full free refund and
            # never create a negative balance. Record the unbilled overage for
            # operations and hard-stop future work at the normal balance gate.
            settled_actual = row.reserved_credits
            adjustment = 0
            settlement_status = "SETTLED_CAPPED"
        else:
            consume_credits(
                db,
                user_id,
                "credit_settlement",
                extra,
                {**(metadata or {}), "phase": "settlement", "reservation_id": row.id},
                idempotency_key=f"{settlement_key}:extra",
            )

    settlement = CreditSettlementRecord(
        reservation_id=row.id,
        user_id=user_id,
        idempotency_key=settlement_key,
        requested_actual_credits=requested_actual,
        settled_credits=settled_actual,
        adjustment=adjustment,
        status=settlement_status,
        metadata_json={
            **(metadata or {}),
            "unbilled_credits": max(0, requested_actual - settled_actual),
        },
    )
    db.add(settlement)
    row.status = settlement_status
    row.settled_credits = settled_actual
    row.completed_at = datetime.now(timezone.utc)
    db.flush()
    return CreditSettlement(
        reserved=row.reserved_credits,
        actual=settled_actual,
        adjustment=adjustment,
    )


def refund_task(
    db: Session,
    user_id: str,
    reservation: CreditReservation,
    reason: str,
    metadata: dict | None = None,
) -> CreditSettlement:
    row = (
        db.query(CreditReservationRecord)
        .filter_by(user_id=user_id, idempotency_key=reservation.idempotency_key)
        .with_for_update()
        .one_or_none()
    )
    if not row:
        raise ValueError("Credit reservation not found")
    existing = db.query(CreditRefundEvent).filter_by(reservation_id=row.id).one_or_none()
    if existing or row.status == "REFUNDED":
        return CreditSettlement(
            reserved=row.reserved_credits,
            actual=0,
            adjustment=row.reserved_credits,
        )
    settlement = db.query(CreditSettlementRecord).filter_by(reservation_id=row.id).one_or_none()
    if settlement or row.status.startswith("SETTLED"):
        raise ValueError("Settled reservation cannot be fully refunded")

    refund_key = f"credit-refund:{row.idempotency_key}"
    refund_credits(
        db,
        user_id,
        "credit_refund",
        row.reserved_credits,
        {**(metadata or {}), "reason": reason, "phase": "refund", "reservation_id": row.id},
        idempotency_key=refund_key,
    )
    db.add(
        CreditRefundEvent(
            reservation_id=row.id,
            user_id=user_id,
            idempotency_key=refund_key,
            credits=row.reserved_credits,
            reason=reason[:200],
            metadata_json=metadata or {},
        )
    )
    row.status = "REFUNDED"
    row.settled_credits = 0
    row.completed_at = datetime.now(timezone.utc)
    db.flush()
    return CreditSettlement(
        reserved=row.reserved_credits,
        actual=0,
        adjustment=row.reserved_credits,
    )


def recover_stale_reservations(
    db: Session,
    *,
    older_than_minutes: int = 360,
    limit: int = 100,
) -> int:
    """Refund abandoned reservations after the maximum execution window."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    query = (
        db.query(CreditReservationRecord)
        .filter(
            CreditReservationRecord.status == "RESERVED",
            CreditReservationRecord.created_at < cutoff,
        )
        .order_by(CreditReservationRecord.created_at)
        .limit(limit)
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    rows = query.all()
    for row in rows:
        refund_task(
            db,
            row.user_id,
            CreditReservation(idempotency_key=row.idempotency_key, credits=row.reserved_credits),
            "STALE_RESERVATION_RECOVERY",
            metadata={"task_type": row.task_type, "created_at": row.created_at.isoformat()},
        )
    db.commit()
    return len(rows)
