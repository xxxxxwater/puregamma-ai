"""LIVE mandate proposals: propose -> two-person approval -> effective.

Before this module there was no product path that creates or changes a LIVE
mandate; rows were inserted by operators. This is the reviewed path, off by
default (``LIVE_MANDATE_PROPOSALS_ENABLED``).

State machine (``TradingMandateProposal.status``)::

    pending --approve (admin #1)--> pending [1 approval]
    pending [1 approval] --approve (admin #2)--> applied
    pending --reject (admin, reason)--> rejected
    pending --revoke (proposer, owner or admin, reason)--> revoked
    pending --expires_at passes--> expired          (checked on every touch)

Rules:

- approvers are administrators; an approver may not be the proposer or the
  mandate owner, and the two approvals must come from two different people;
- the terms are validated when proposed and again when applied (ownership of
  account/release/connection, decimal limits, spot-only leverage, the user's
  approved notional cap);
- a proposal cannot become effective while a global or user kill switch is
  engaged (it stays pending until released or expired); an amendment cannot
  apply to a mandate whose own kill switch is engaged, or whose revision moved
  since the proposal was made;
- applying never enables LIVE: a new mandate starts paused (the owner resumes
  it with the exact phrase, which re-evaluates every gate), and every order
  still passes ``flags.evaluate_full_gate`` including the deployment's static
  gate. Nothing here reads or changes ``LIVE_TRADING_*`` settings;
- each transition is under the proposal row lock and appends an audit row;
  creating the mandate uses a unique idempotency key, so a race can never
  produce two mandates from one proposal.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import (
    BrokerConnection,
    LiveUserApproval,
    StrategyRelease,
    TradingAccount,
    TradingMandate,
    TradingMandateProposal,
    User,
    utcnow,
)
from packages.live_trading import kill_switch as kill_switch_service
from packages.live_trading.audit import audit, new_trace_id
from packages.live_trading.decimal_text import decimal_text

TABLE = TradingMandateProposal.__tablename__
REQUIRED_APPROVALS = 2
PENDING, APPLIED, REJECTED, REVOKED, EXPIRED = "pending", "applied", "rejected", "revoked", "expired"
_DECIMAL_FIELDS = ("max_total_notional", "max_per_order_notional", "max_position_notional", "max_daily_loss", "max_leverage")
_AMENDABLE = (
    "allowed_symbols", "allowed_side", *_DECIMAL_FIELDS, "max_trades_per_day", "max_order_frequency_seconds", "mandate_expires_at",
)
NEW_MANDATE_PAUSE_REASON = "dual_approval_applied: owner must resume"


class ProposalsDisabled(RuntimeError):
    """The feature flag is off (HTTP 404: the surface does not exist)."""


class ProposalsUnavailable(RuntimeError):
    """Flag on but migration 0036 not applied (HTTP 503)."""


class ProposalInvalid(ValueError):
    """The terms are not acceptable (HTTP 400)."""


class ProposalForbidden(PermissionError):
    """This actor may not perform this transition (HTTP 403)."""


class ProposalConflict(RuntimeError):
    """The transition is not possible in the proposal's current state (HTTP 409)."""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None


def ensure_available(db: Session) -> None:
    """Fail closed: off unless the flag is on AND the table exists."""
    if not get_settings().live_mandate_proposals_enabled:
        raise ProposalsDisabled("Mandate proposals are not enabled on this deployment")
    try:
        ready = inspect(db.get_bind()).has_table(TABLE)
    except Exception as exc:  # noqa: BLE001 - any inspection failure means "not ready"
        raise ProposalsUnavailable("Mandate proposals are unavailable") from exc
    if not ready:
        raise ProposalsUnavailable("Mandate proposals need database migration 0036, which has not been applied")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _decimal(terms: dict, key: str) -> Decimal:
    raw = terms.get(key)
    if raw is None or isinstance(raw, bool) or isinstance(raw, float):
        raise ProposalInvalid(f"{key} must be a decimal string")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ProposalInvalid(f"{key} must be a decimal string") from exc
    if not value.is_finite() or value <= 0:
        raise ProposalInvalid(f"{key} must be a positive decimal")
    return value


def _int(terms: dict, key: str, low: int, high: int) -> int:
    raw = terms.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int) or not low <= raw <= high:
        raise ProposalInvalid(f"{key} must be an integer between {low} and {high}")
    return raw


def _normalize_terms(db: Session, user_id: str, terms: dict) -> dict:
    """Validate and canonicalize mandate terms (decimals as strings)."""
    symbols = terms.get("allowed_symbols")
    if not isinstance(symbols, list) or not symbols or len(symbols) > 20:
        raise ProposalInvalid("allowed_symbols must list 1-20 symbols")
    clean_symbols = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not symbol.strip() or len(symbol) > 32 or not symbol.strip().isalnum():
            raise ProposalInvalid("allowed_symbols contains an invalid symbol")
        clean_symbols.append(symbol.strip().upper())
    deployment_symbols = {item.upper() for item in get_settings().live_trading_allowed_symbols}
    if deployment_symbols and not set(clean_symbols) <= deployment_symbols:
        raise ProposalInvalid("allowed_symbols must be within the deployment whitelist")
    side = terms.get("allowed_side", "both")
    if side not in {"long", "both"}:
        # Spot only: no shorting.
        raise ProposalInvalid("allowed_side must be long or both")
    total = _decimal(terms, "max_total_notional")
    per_order = _decimal(terms, "max_per_order_notional")
    position = _decimal(terms, "max_position_notional")
    daily_loss = _decimal(terms, "max_daily_loss")
    leverage = _decimal(terms, "max_leverage")
    if leverage != Decimal("1"):
        raise ProposalInvalid("max_leverage must be 1 (spot only)")
    if not per_order <= position <= total:
        raise ProposalInvalid("limits must satisfy per-order <= position <= total")
    if daily_loss > total:
        raise ProposalInvalid("max_daily_loss cannot exceed max_total_notional")
    trades = _int(terms, "max_trades_per_day", 1, 1000)
    frequency = _int(terms, "max_order_frequency_seconds", 1, 86400)
    expires = terms.get("mandate_expires_at")
    expires_text = None
    if expires is not None:
        try:
            parsed = _aware(datetime.fromisoformat(str(expires).replace("Z", "+00:00")))
        except ValueError as exc:
            raise ProposalInvalid("mandate_expires_at must be an ISO timestamp") from exc
        now = datetime.now(timezone.utc)
        if not now < parsed <= now + timedelta(days=366):
            raise ProposalInvalid("mandate_expires_at must be in the future and within a year")
        expires_text = parsed.isoformat()
    return {
        "allowed_symbols": clean_symbols,
        "allowed_side": side,
        "max_total_notional": decimal_text(total),
        "max_per_order_notional": decimal_text(per_order),
        "max_position_notional": decimal_text(position),
        "max_daily_loss": decimal_text(daily_loss),
        "max_leverage": decimal_text(leverage),
        "max_trades_per_day": trades,
        "max_order_frequency_seconds": frequency,
        "mandate_expires_at": expires_text,
    }


def _check_bindings(db: Session, user_id: str, binding: dict) -> dict:
    account = db.query(TradingAccount).filter_by(id=binding.get("account_id"), user_id=user_id).one_or_none()
    if account is None or account.status != "ACTIVE":
        raise ProposalInvalid("account_id must be an active account of the mandate owner")
    release = db.query(StrategyRelease).filter_by(id=binding.get("strategy_release_id"), user_id=user_id).one_or_none()
    if release is None or release.review_status != "approved":
        raise ProposalInvalid("strategy_release_id must be an approved release of the mandate owner")
    connection_id = binding.get("broker_connection_id")
    if connection_id:
        connection = db.query(BrokerConnection).filter_by(id=connection_id, user_id=user_id).one_or_none()
        if connection is None or connection.revoked_at is not None:
            raise ProposalInvalid("broker_connection_id must be an unrevoked connection of the mandate owner")
    return {"account_id": account.id, "strategy_release_id": release.id, "broker_connection_id": connection_id or None}


def _check_user_cap(db: Session, user_id: str, total: str) -> None:
    approval = db.query(LiveUserApproval).filter_by(user_id=user_id).one_or_none()
    if approval is None or approval.status != "approved":
        raise ProposalConflict("The mandate owner has no approved LIVE eligibility")
    if Decimal(total) > Decimal(str(approval.max_total_notional or 0)):
        raise ProposalInvalid("max_total_notional exceeds the owner's approved LIVE cap")


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


def _audit(db: Session, proposal: TradingMandateProposal, actor: User, action: str, request: dict, actor_type: str) -> None:
    audit(
        db,
        user_id=proposal.user_id,
        action=action,
        status=proposal.status.upper(),
        trace_id=proposal.trace_id,
        idempotency_key=f"audit:mandate-proposal:{proposal.id}:{action.lower()}:{uuid.uuid4().hex}",
        actor_type=actor_type,
        request_json={"proposal_id": proposal.id, "actor_user_id": actor.id, **request},
        result_json={"status": proposal.status, "approvals": len(proposal.approvals_json or [])},
    )


def _expire_if_due(proposal: TradingMandateProposal) -> bool:
    if proposal.status == PENDING and _aware(proposal.expires_at) <= datetime.now(timezone.utc):
        proposal.status = EXPIRED
        proposal.decided_at = utcnow()
        proposal.decision_reason = "expired before two approvals"
        return True
    return False


def serialize(proposal: TradingMandateProposal) -> dict:
    return {
        "id": proposal.id,
        "kind": proposal.kind,
        "user_id": proposal.user_id,
        "target_mandate_id": proposal.target_mandate_id,
        "base_revision": proposal.base_revision,
        "proposed_by": proposal.proposed_by,
        "terms": proposal.payload_json or {},
        "status": proposal.status,
        "approvals": list(proposal.approvals_json or []),
        "required_approvals": REQUIRED_APPROVALS,
        "decided_by": proposal.decided_by,
        "decided_at": _iso(proposal.decided_at),
        "decision_reason": proposal.decision_reason,
        "expires_at": _iso(proposal.expires_at),
        "applied_mandate_id": proposal.applied_mandate_id,
        "created_at": _iso(proposal.created_at),
    }


def propose(
    db: Session,
    actor: User,
    *,
    user_id: str,
    terms: dict,
    target_mandate_id: str | None = None,
    reason: str,
) -> dict:
    """Create a pending proposal. An owner may propose for themselves; an
    administrator may propose for any user."""
    ensure_available(db)
    reason = (reason or "").strip()
    if not reason:
        raise ProposalInvalid("A reason is required")
    if actor.id != user_id and actor.role != "admin":
        raise LookupError("User not found")
    if db.query(User).filter_by(id=user_id).one_or_none() is None:
        raise LookupError("User not found")
    normalized = _normalize_terms(db, user_id, terms)
    if target_mandate_id:
        mandate = db.query(TradingMandate).filter_by(id=target_mandate_id, user_id=user_id).one_or_none()
        if mandate is None:
            raise LookupError("Trading mandate not found")
        if mandate.revoked_at is not None or mandate.status in {"revoked", "expired"}:
            raise ProposalConflict("A revoked or expired mandate cannot be amended")
        kind, base_revision = "amend", mandate.revision
        payload = normalized
    else:
        kind, base_revision = "create", None
        payload = {**_check_bindings(db, user_id, terms), **normalized}
    ttl = timedelta(hours=get_settings().live_mandate_proposal_ttl_hours)
    proposal = TradingMandateProposal(
        kind=kind,
        user_id=user_id,
        target_mandate_id=target_mandate_id,
        base_revision=base_revision,
        proposed_by=actor.id,
        payload_json=payload,
        status=PENDING,
        approvals_json=[],
        expires_at=utcnow() + ttl,
        idempotency_key=f"mandate-proposal:{uuid.uuid4().hex}",
        trace_id=new_trace_id(),
    )
    db.add(proposal)
    db.flush()
    _audit(db, proposal, actor, "LIVE_MANDATE_PROPOSED", {"reason": reason, "kind": kind}, "admin" if actor.role == "admin" else "user")
    db.commit()
    db.refresh(proposal)
    return serialize(proposal)


def _locked(db: Session, proposal_id: str) -> TradingMandateProposal:
    proposal = db.query(TradingMandateProposal).filter_by(id=proposal_id).with_for_update().one_or_none()
    if proposal is None:
        raise LookupError("Proposal not found")
    return proposal


def _close_expired(db: Session, proposal: TradingMandateProposal, actor: User) -> None:
    if _expire_if_due(proposal):
        _audit(db, proposal, actor, "LIVE_MANDATE_PROPOSAL_EXPIRED", {}, "system")
        db.commit()
        raise ProposalConflict("The proposal has expired")


def approve(db: Session, admin: User, proposal_id: str, *, note: str) -> dict:
    ensure_available(db)
    if admin.role != "admin":
        raise ProposalForbidden("Only administrators approve mandate proposals")
    note = (note or "").strip()
    if not note:
        raise ProposalInvalid("A note is required")
    proposal = _locked(db, proposal_id)
    _close_expired(db, proposal, admin)
    if proposal.status != PENDING:
        db.rollback()
        raise ProposalConflict(f"The proposal is {proposal.status}")
    if admin.id == proposal.proposed_by:
        db.rollback()
        raise ProposalForbidden("The proposer cannot approve their own proposal")
    if admin.id == proposal.user_id:
        db.rollback()
        raise ProposalForbidden("The mandate owner cannot approve their own mandate")
    approvals = list(proposal.approvals_json or [])
    if any(item.get("approver_id") == admin.id for item in approvals):
        db.rollback()
        raise ProposalForbidden("The same administrator cannot approve twice")
    if len(approvals) + 1 >= REQUIRED_APPROVALS:
        blocked = _kill_switch_block(db, proposal)
        if blocked:
            db.rollback()
            raise ProposalConflict(f"Cannot take effect while a {blocked} kill switch is engaged")
    approvals.append({"approver_id": admin.id, "at": utcnow().isoformat(), "note": note})
    proposal.approvals_json = approvals
    if len(approvals) >= REQUIRED_APPROVALS:
        try:
            _apply(db, proposal, admin)
        except Exception:
            # Nothing is half-applied: the approval, the mandate and the
            # status change are one transaction.
            db.rollback()
            raise
    _audit(db, proposal, admin, "LIVE_MANDATE_PROPOSAL_APPROVED", {"note": note, "approval_number": len(approvals)}, "admin")
    db.commit()
    db.refresh(proposal)
    return serialize(proposal)


def _kill_switch_block(db: Session, proposal: TradingMandateProposal) -> str | None:
    if kill_switch_service.is_engaged(db, "global"):
        return "global"
    if kill_switch_service.is_engaged(db, "user", proposal.user_id):
        return "user"
    if proposal.target_mandate_id and kill_switch_service.is_engaged(db, "mandate", proposal.target_mandate_id):
        return "mandate"
    return None


def _apply(db: Session, proposal: TradingMandateProposal, approver: User) -> None:
    terms = dict(proposal.payload_json or {})
    # Re-validate against the state at the moment of effect.
    normalized = _normalize_terms(db, proposal.user_id, terms)
    _check_user_cap(db, proposal.user_id, normalized["max_total_notional"])
    expires = datetime.fromisoformat(normalized["mandate_expires_at"]) if normalized["mandate_expires_at"] else None
    limits = {key: Decimal(normalized[key]) for key in _DECIMAL_FIELDS}
    approvers = [item["approver_id"] for item in proposal.approvals_json]
    if proposal.kind == "create":
        binding = _check_bindings(db, proposal.user_id, terms)
        mandate = TradingMandate(
            user_id=proposal.user_id,
            account_id=binding["account_id"],
            strategy_release_id=binding["strategy_release_id"],
            broker_connection_id=binding["broker_connection_id"],
            execution_mode="live",
            environment="production",
            status="active",
            allowed_symbols_json=normalized["allowed_symbols"],
            allowed_side=normalized["allowed_side"],
            max_trades_per_day=normalized["max_trades_per_day"],
            max_order_frequency_seconds=normalized["max_order_frequency_seconds"],
            kill_switch_state="inactive",
            # Effective but not trading: the owner resumes it explicitly, and
            # resume re-evaluates every gate.
            paused=True,
            pause_reason=NEW_MANDATE_PAUSE_REASON,
            approval_status="approved",
            approved_by=approver.id,
            approved_at=utcnow(),
            expires_at=expires,
            audit_metadata_json={"proposal_id": proposal.id, "approvers": approvers, "proposed_by": proposal.proposed_by},
            idempotency_key=f"mandate:proposal:{proposal.id}",
            **limits,
        )
        db.add(mandate)
        db.flush()
    else:
        mandate = (
            db.query(TradingMandate)
            .filter_by(id=proposal.target_mandate_id, user_id=proposal.user_id)
            .with_for_update()
            .one_or_none()
        )
        if mandate is None:
            raise ProposalConflict("The target mandate no longer exists")
        if mandate.revision != proposal.base_revision:
            raise ProposalConflict("The mandate changed since this amendment was proposed; propose again")
        if mandate.revoked_at is not None or mandate.status in {"revoked", "expired"}:
            raise ProposalConflict("A revoked or expired mandate cannot be amended")
        if mandate.kill_switch_state == "active":
            raise ProposalConflict("Cannot amend a mandate whose kill switch is engaged")
        for key, value in limits.items():
            setattr(mandate, key, value)
        mandate.allowed_symbols_json = normalized["allowed_symbols"]
        mandate.allowed_side = normalized["allowed_side"]
        mandate.max_trades_per_day = normalized["max_trades_per_day"]
        mandate.max_order_frequency_seconds = normalized["max_order_frequency_seconds"]
        mandate.expires_at = expires
        mandate.revision = (mandate.revision or 1) + 1
        mandate.approved_by = approver.id
        mandate.approved_at = utcnow()
        meta = dict(mandate.audit_metadata_json or {})
        meta.setdefault("amendments", []).append({"proposal_id": proposal.id, "approvers": approvers, "revision": mandate.revision})
        mandate.audit_metadata_json = meta
    proposal.status = APPLIED
    proposal.applied_mandate_id = mandate.id
    proposal.decided_by = approver.id
    proposal.decided_at = utcnow()


def reject(db: Session, admin: User, proposal_id: str, *, reason: str) -> dict:
    ensure_available(db)
    if admin.role != "admin":
        raise ProposalForbidden("Only administrators reject mandate proposals")
    return _close(db, admin, proposal_id, REJECTED, reason, "LIVE_MANDATE_PROPOSAL_REJECTED", "admin")


def revoke(db: Session, actor: User, proposal_id: str, *, reason: str) -> dict:
    """The proposer, the mandate owner or any administrator can withdraw a
    pending proposal. Anyone else gets the same 404 as for a nonexistent one."""
    ensure_available(db)
    proposal = db.query(TradingMandateProposal).filter_by(id=proposal_id).one_or_none()
    if proposal is None or (actor.role != "admin" and actor.id not in {proposal.proposed_by, proposal.user_id}):
        raise LookupError("Proposal not found")
    return _close(db, actor, proposal_id, REVOKED, reason, "LIVE_MANDATE_PROPOSAL_REVOKED", "admin" if actor.role == "admin" else "user")


def _close(db: Session, actor: User, proposal_id: str, status: str, reason: str, action: str, actor_type: str) -> dict:
    reason = (reason or "").strip()
    if not reason:
        raise ProposalInvalid("A reason is required")
    proposal = _locked(db, proposal_id)
    _close_expired(db, proposal, actor)
    if proposal.status != PENDING:
        db.rollback()
        raise ProposalConflict(f"The proposal is {proposal.status}")
    proposal.status = status
    proposal.decided_by = actor.id
    proposal.decided_at = utcnow()
    proposal.decision_reason = reason
    _audit(db, proposal, actor, action, {"reason": reason}, actor_type)
    db.commit()
    db.refresh(proposal)
    return serialize(proposal)


def list_for_user(db: Session, user_id: str, *, limit: int = 50) -> list[dict]:
    ensure_available(db)
    rows = (
        db.query(TradingMandateProposal)
        .filter(TradingMandateProposal.user_id == user_id)
        .order_by(TradingMandateProposal.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [serialize(_lazily_expired(db, row)) for row in rows]


def list_all(db: Session, *, status: str | None = None, limit: int = 50) -> list[dict]:
    ensure_available(db)
    query = db.query(TradingMandateProposal)
    if status:
        query = query.filter(TradingMandateProposal.status == status)
    rows = query.order_by(TradingMandateProposal.created_at.desc()).limit(max(1, min(limit, 200))).all()
    return [serialize(_lazily_expired(db, row)) for row in rows]


def _lazily_expired(db: Session, row: TradingMandateProposal) -> TradingMandateProposal:
    """Reads report an overdue pending proposal as expired without writing;
    the transition is persisted (and audited) by the next action on it."""
    if row.status == PENDING and _aware(row.expires_at) <= datetime.now(timezone.utc):
        db.expunge(row)
        row.status = EXPIRED
    return row
