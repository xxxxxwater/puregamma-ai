from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import CreditLedger, User


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
    if not get_settings().credit_usage_enforced:
        return _ledger(db, user, f"{action}_refund", 0, {**(metadata or {}), "credits_bypassed": amount}, idempotency_key)
    user.credit_balance += amount
    return _ledger(db, user, f"{action}_refund", amount, metadata, idempotency_key)


def grant_credits(db: Session, user_id: str, action: str, amount: int, metadata: dict | None = None) -> CreditLedger:
    if amount < 0:
        raise ValueError("Credit amount must be non-negative")
    user = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if not user:
        raise ValueError(f"User not found: {user_id}")
    user.credit_balance += amount
    return _ledger(db, user, action, amount, metadata)
