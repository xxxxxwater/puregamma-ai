from __future__ import annotations

from sqlalchemy.orm import Session

from packages.database.models import CreditLedger, User


class InsufficientCreditsError(RuntimeError):
    pass


def _ledger(db: Session, user: User, action: str, delta: int, metadata: dict | None = None) -> CreditLedger:
    entry = CreditLedger(
        user_id=user.id,
        action=action,
        credits_delta=delta,
        balance_after=user.credit_balance,
        metadata_json=metadata or {},
    )
    db.add(entry)
    db.flush()
    return entry


def consume_credits(db: Session, user_id: str, action: str, amount: int, metadata: dict | None = None) -> CreditLedger:
    if amount < 0:
        raise ValueError("Credit amount must be non-negative")
    user = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if not user:
        raise ValueError(f"User not found: {user_id}")
    return _ledger(db, user, action, 0, {**(metadata or {}), "credits_bypassed": amount})


def refund_credits(db: Session, user_id: str, action: str, amount: int, metadata: dict | None = None) -> CreditLedger:
    if amount < 0:
        raise ValueError("Credit amount must be non-negative")
    user = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if not user:
        raise ValueError(f"User not found: {user_id}")
    return _ledger(db, user, f"{action}_refund", 0, {**(metadata or {}), "credits_bypassed": amount})


def grant_credits(db: Session, user_id: str, action: str, amount: int, metadata: dict | None = None) -> CreditLedger:
    if amount < 0:
        raise ValueError("Credit amount must be non-negative")
    user = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if not user:
        raise ValueError(f"User not found: {user_id}")
    user.credit_balance += amount
    return _ledger(db, user, action, amount, metadata)
