from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.services.credit_service import quote_task, reserve_task, settle_task
from apps.api.services import custody_service
from apps.api.services.entitlement_service import get_user_entitlement
from packages.database.models import (
    AccountSnapshot,
    OrderIntent,
    OrderJournal,
    PositionSnapshot,
    ReconciliationRecord,
    RiskDecision,
    StrategyRun,
    TradingAccount,
    TradingAuditLog,
    utcnow,
)
from packages.trading.policies.safety import (
    assert_execution_mode_allowed,
    confirmation_hash,
)
from packages.trading.runtime_client import NautilusRuntimeClient
from packages.trading.schemas.models import OrderPreview


class TradingServiceError(RuntimeError):
    pass


def owned_account(db: Session, user_id: str, account_id: str) -> TradingAccount:
    row = (
        db.query(TradingAccount).filter_by(id=account_id, user_id=user_id).one_or_none()
    )
    if not row:
        raise LookupError("Trading account not found")
    return row


def list_accounts(db: Session, user_id: str) -> list[dict]:
    rows = (
        db.query(TradingAccount)
        .filter_by(user_id=user_id)
        .order_by(TradingAccount.created_at)
        .all()
    )
    return [
        {
            "id": row.id,
            "name": row.name,
            "venue": row.venue,
            "account_type": row.account_type,
            "base_currency": row.base_currency,
            "status": row.status,
            "permissions": row.permissions_json,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def list_positions(
    db: Session, user_id: str, account_id: str | None = None
) -> list[dict]:
    query = db.query(PositionSnapshot).filter_by(user_id=user_id)
    if account_id:
        owned_account(db, user_id, account_id)
        query = query.filter_by(account_id=account_id)
    history = query.order_by(PositionSnapshot.captured_at.desc()).limit(500).all()
    rows = []
    seen = set()
    for row in history:
        key = (row.account_id, row.instrument)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return [
        {
            "id": row.id,
            "account_id": row.account_id,
            "strategy_id": row.strategy_id,
            "run_id": row.run_id,
            "instrument": row.instrument,
            "quantity": row.quantity,
            "side": row.side,
            "average_price": row.average_price,
            "mark_price": row.mark_price,
            "unrealized_pnl": row.unrealized_pnl,
            "realized_pnl": row.realized_pnl,
            "leverage": row.leverage,
            "captured_at": row.captured_at.isoformat(),
        }
        for row in rows
    ]


def account_performance(
    db: Session, user_id: str, account_id: str | None = None
) -> dict:
    query = db.query(AccountSnapshot).filter_by(user_id=user_id)
    if account_id:
        owned_account(db, user_id, account_id)
        query = query.filter_by(account_id=account_id)
    rows = query.order_by(AccountSnapshot.captured_at.desc()).limit(100).all()
    latest = {}
    for row in rows:
        latest.setdefault(row.account_id, row)
    return {
        "accounts": [
            {
                "account_id": row.account_id,
                "balance": row.balance,
                "equity": row.equity,
                "available_margin": row.available_margin,
                "daily_pnl": row.daily_pnl,
                "drawdown": row.drawdown,
                "exposure": row.exposure,
                "stale": row.stale,
                "captured_at": row.captured_at.isoformat(),
            }
            for row in latest.values()
        ]
    }


def list_orders(db: Session, user_id: str, account_id: str | None = None) -> list[dict]:
    query = db.query(OrderJournal).filter_by(user_id=user_id)
    if account_id:
        owned_account(db, user_id, account_id)
        query = query.filter_by(account_id=account_id)
    rows = query.order_by(OrderJournal.created_at.desc()).limit(300).all()
    return [serialize_order(row) for row in rows]


def preview_order(
    db: Session, user_id: str, payload: dict, *, conversation_id: str | None = None
) -> tuple[OrderIntent, str]:
    entitlement = get_user_entitlement(db, user_id)
    if not entitlement["high_cost_tasks"]:
        raise TradingServiceError(
            "Manual paper order preview requires an active paid entitlement"
        )
    order = OrderPreview.model_validate(payload)
    assert_execution_mode_allowed(order.execution_mode)
    if order.execution_mode.value not in {"PAPER", "SHADOW"}:
        raise TradingServiceError("Only PAPER and SHADOW orders are available")
    account = owned_account(db, user_id, order.account_id)
    permission = (
        "paper_order" if order.execution_mode.value == "PAPER" else "shadow_order"
    )
    if not account.permissions_json.get(permission):
        raise TradingServiceError("Account does not allow this execution mode")
    existing = (
        db.query(OrderIntent)
        .filter_by(idempotency_key=order.idempotency_key, user_id=user_id)
        .one_or_none()
    )
    if existing:
        return existing, ""
    quote = quote_task(task_type="manual_order_preview")
    reservation = reserve_task(
        db,
        user_id,
        quote,
        f"manual-order-preview:{user_id}:{order.idempotency_key}",
        {"order_idempotency_key": order.idempotency_key},
    )
    token = f"CONFIRM ORDER {order.instrument} {order.direction.upper()} {order.quantity} {secrets.token_urlsafe(18)}"
    row = OrderIntent(
        user_id=user_id,
        conversation_id=conversation_id,
        strategy_id=order.strategy_id,
        account_id=account.id,
        instrument=order.instrument.upper(),
        venue=order.venue.upper(),
        direction=order.direction.upper(),
        quantity=order.quantity,
        notional=order.notional,
        leverage=order.leverage,
        order_type=order.order_type.upper(),
        reduce_only=order.reduce_only,
        execution_mode=order.execution_mode.value,
        status="PREVIEWED",
        risk_limits_json={},
        idempotency_key=order.idempotency_key,
        confirmation_token_hash=confirmation_hash(token),
        approval_status="PENDING",
        expires_at=utcnow() + timedelta(minutes=10),
        raw_event_reference={},
    )
    db.add(row)
    db.flush()
    db.add(
        TradingAuditLog(
            user_id=user_id,
            conversation_id=conversation_id,
            strategy_id=order.strategy_id,
            action="PREVIEW_MANUAL_ORDER",
            status="PENDING_CONFIRMATION",
            actor_type="user",
            request_json=order.model_dump(mode="json"),
            result_json={"order_intent_id": row.id},
            idempotency_key=f"audit:{order.idempotency_key}",
        )
    )
    settle_task(db, user_id, reservation, quote.credits, metadata={"order_intent_id": row.id})
    db.commit()
    db.refresh(row)
    return row, token


def confirm_order(
    db: Session,
    user_id: str,
    order_intent_id: str,
    confirmation: str,
    *,
    runtime: NautilusRuntimeClient | None = None,
) -> OrderJournal:
    intent = (
        db.query(OrderIntent)
        .filter_by(id=order_intent_id, user_id=user_id)
        .one_or_none()
    )
    if not intent:
        raise LookupError("Order intent not found")
    existing = (
        db.query(OrderJournal)
        .filter_by(order_intent_id=intent.id, user_id=user_id)
        .order_by(OrderJournal.sequence.desc())
        .first()
    )
    if existing:
        return existing
    if intent.approval_status != "PENDING" or intent.status != "PREVIEWED":
        raise TradingServiceError("Order preview is no longer pending")
    expires = (
        intent.expires_at
        if intent.expires_at.tzinfo
        else intent.expires_at.replace(tzinfo=timezone.utc)
    )
    if expires < datetime.now(timezone.utc):
        raise TradingServiceError("Order confirmation expired")
    if not secrets.compare_digest(
        intent.confirmation_token_hash or "", confirmation_hash(confirmation)
    ):
        raise TradingServiceError(
            "Explicit order confirmation does not match the preview"
        )
    assert_execution_mode_allowed(intent.execution_mode)
    account = owned_account(db, user_id, intent.account_id)
    # Custody-linked accounts hold the quote notional at submission time.
    # Unlinked accounts are a no-op here (behavior unchanged). The freeze is
    # idempotent on the intent id and happens in this transaction, so a
    # rejected order releases the hold below and a failed commit rolls it back.
    try:
        custody_service.apply_order_freeze(
            db,
            trading_account=account,
            user_id=user_id,
            order_ref=intent.id,
            side=intent.direction,
            notional=intent.notional,
            quote_asset=account.base_currency,
        )
    except custody_service.InsufficientCustodyBalance as exc:
        raise TradingServiceError("Insufficient custody balance for this order") from exc
    run = (
        db.query(StrategyRun)
        .filter_by(strategy_id=intent.strategy_id, user_id=user_id)
        .order_by(StrategyRun.created_at.desc())
        .first()
        if intent.strategy_id
        else None
    )
    client_order_id = f"pg-{uuid.uuid4().hex[:20]}"
    runtime_payload = {
        "client_order_id": client_order_id,
        "account_id": account.id,
        "strategy_id": intent.strategy_id,
        "run_id": run.runtime_run_id if run else None,
        "instrument": intent.instrument,
        "venue": intent.venue,
        "direction": intent.direction,
        "side": intent.direction,
        "quantity": intent.quantity,
        "notional": intent.notional,
        "leverage": intent.leverage,
        "order_type": intent.order_type,
        "reduce_only": intent.reduce_only,
        "mode": intent.execution_mode,
        "risk_policy": intent.risk_limits_json,
        "idempotency_key": intent.idempotency_key,
    }
    ack = (runtime or NautilusRuntimeClient()).command(
        "submit_order", f"order:{intent.id}", runtime_payload
    )
    state = ack.get("state", "REJECTED")
    journal = OrderJournal(
        user_id=user_id,
        account_id=account.id,
        strategy_id=intent.strategy_id,
        run_id=run.id if run else None,
        order_intent_id=intent.id,
        client_order_id=client_order_id,
        exchange_order_id=ack.get("exchange_order_id"),
        sequence=int(ack.get("sequence", 1)),
        state=state,
        instrument=intent.instrument,
        side=intent.direction,
        quantity=intent.quantity,
        filled_quantity=float(ack.get("filled_quantity", 0)),
        remaining_quantity=float(ack.get("remaining_quantity", intent.quantity)),
        average_price=ack.get("average_price"),
        reduce_only=intent.reduce_only,
        event_json=ack,
        raw_event_reference={},
        idempotency_key=f"journal:{intent.id}:{ack.get('sequence', 1)}",
        error_message=ack.get("error"),
    )
    db.add(journal)
    db.flush()  # journal.id feeds the custody fill idempotency reference
    # Custody settlement for the ack: fills debit the frozen hold (BUY) or
    # credit proceeds (SELL); rejects release the hold.
    if state == "REJECTED":
        custody_service.release_order_freeze(
            db,
            trading_account=account,
            user_id=user_id,
            order_ref=intent.id,
            side=intent.direction,
            notional=intent.notional,
            quote_asset=account.base_currency,
        )
    else:
        custody_service.apply_fill_settlement(
            db,
            trading_account=account,
            user_id=user_id,
            fill_ref=journal.id,
            side=intent.direction,
            state=state,
            quantity=intent.quantity,
            filled_quantity=float(ack.get("filled_quantity", 0)),
            average_price=ack.get("average_price"),
            notional=intent.notional,
            quote_asset=account.base_currency,
        )
    decision = ack.get(
        "risk_decision",
        {
            "decision": "REJECT",
            "reasons": [ack.get("error", "RUNTIME_REJECTED")],
            "limits": {},
            "state": {},
        },
    )
    db.add(
        RiskDecision(
            user_id=user_id,
            strategy_id=intent.strategy_id,
            run_id=run.id if run else None,
            order_intent_id=intent.id,
            decision=decision["decision"],
            reasons=decision.get("reasons", []),
            limits_json=decision.get("limits", {}),
            state_json=decision.get("state", {}),
        )
    )
    intent.approval_status = "APPROVED"
    intent.status = "EXECUTED" if state != "REJECTED" else "REJECTED"
    db.add(
        TradingAuditLog(
            user_id=user_id,
            conversation_id=intent.conversation_id,
            strategy_id=intent.strategy_id,
            run_id=run.id if run else None,
            action="SUBMIT_MANUAL_ORDER",
            status=state,
            actor_type="user",
            request_json={"order_intent_id": intent.id},
            result_json=ack,
            idempotency_key=f"audit:order:{intent.id}",
        )
    )
    db.commit()
    db.refresh(journal)
    return journal


def cancel_order(
    db: Session,
    user_id: str,
    client_order_id: str,
    *,
    runtime: NautilusRuntimeClient | None = None,
) -> OrderJournal:
    current = (
        db.query(OrderJournal)
        .filter_by(client_order_id=client_order_id, user_id=user_id)
        .order_by(OrderJournal.sequence.desc())
        .first()
    )
    if not current:
        raise LookupError("Order not found")
    if current.state in {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}:
        return current
    ack = (runtime or NautilusRuntimeClient()).command(
        "cancel_order",
        f"cancel:{current.id}",
        {"account_id": current.account_id, "client_order_id": current.client_order_id},
    )
    next_row = OrderJournal(
        user_id=user_id,
        account_id=current.account_id,
        strategy_id=current.strategy_id,
        run_id=current.run_id,
        order_intent_id=current.order_intent_id,
        client_order_id=current.client_order_id,
        exchange_order_id=current.exchange_order_id,
        sequence=current.sequence + 1,
        state=ack.get("state", "UNKNOWN"),
        instrument=current.instrument,
        side=current.side,
        quantity=current.quantity,
        filled_quantity=float(ack.get("filled_quantity", current.filled_quantity)),
        remaining_quantity=float(
            ack.get("remaining_quantity", current.remaining_quantity)
        ),
        average_price=ack.get("average_price", current.average_price),
        reduce_only=current.reduce_only,
        event_json=ack,
        raw_event_reference={},
        idempotency_key=f"journal:cancel:{current.id}",
        error_message=ack.get("error"),
    )
    db.add(next_row)
    db.add(
        TradingAuditLog(
            user_id=user_id,
            strategy_id=current.strategy_id,
            run_id=current.run_id,
            action="CANCEL_ORDER",
            status=next_row.state,
            actor_type="user",
            request_json={"client_order_id": client_order_id},
            result_json=ack,
            idempotency_key=f"audit:cancel:{current.id}",
        )
    )
    db.commit()
    db.refresh(next_row)
    return next_row


def reconcile_account(
    db: Session,
    user_id: str,
    account_id: str,
    *,
    runtime: NautilusRuntimeClient | None = None,
) -> ReconciliationRecord:
    entitlement = get_user_entitlement(db, user_id)
    if not entitlement["high_cost_tasks"]:
        raise TradingServiceError("Reconciliation requires an active paid entitlement")
    account = owned_account(db, user_id, account_id)
    # Reconciliation is a platform safety task. It must run even when the user
    # has no remaining Credits and therefore never consumes the user balance.
    ack = (runtime or NautilusRuntimeClient()).command(
        "reconcile",
        f"reconcile:{account.id}:{int(utcnow().timestamp() // 60)}",
        {"account_id": account.id},
    )
    exchange = ack.get("exchange", {})
    record = ReconciliationRecord(
        user_id=user_id,
        account_id=account.id,
        status=ack.get("status", "ERROR"),
        local_state_json={"orders": ack.get("local_open_orders", [])},
        exchange_state_json=exchange,
        differences_json=ack.get("unknown_orders", []),
        actions_json=["pause_opening"] if ack.get("opening_paused") else [],
        raw_event_reference={"runtime_command_id": ack.get("command_id")},
        completed_at=utcnow(),
    )
    db.add(record)
    snapshot = exchange.get("account")
    if snapshot:
        db.add(
            AccountSnapshot(
                user_id=user_id,
                account_id=account.id,
                balance=snapshot["balance"],
                equity=snapshot["equity"],
                available_margin=snapshot["available_margin"],
                daily_pnl=snapshot["daily_pnl"],
                drawdown=snapshot["drawdown"],
                exposure=snapshot["exposure"],
                stale=snapshot["stale"],
                raw_event_reference={"runtime_command_id": ack.get("command_id")},
            )
        )
    db.commit()
    db.refresh(record)
    return record


def serialize_order(row: OrderJournal) -> dict:
    return {
        "id": row.id,
        "account_id": row.account_id,
        "strategy_id": row.strategy_id,
        "run_id": row.run_id,
        "order_intent_id": row.order_intent_id,
        "client_order_id": row.client_order_id,
        "exchange_order_id": row.exchange_order_id,
        "sequence": row.sequence,
        "state": row.state,
        "instrument": row.instrument,
        "side": row.side,
        "quantity": row.quantity,
        "filled_quantity": row.filled_quantity,
        "remaining_quantity": row.remaining_quantity,
        "average_price": row.average_price,
        "reduce_only": row.reduce_only,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat(),
    }


def serialize_order_intent(row: OrderIntent, confirmation: str = "") -> dict:
    return {
        "id": row.id,
        "account_id": row.account_id,
        "strategy_id": row.strategy_id,
        "instrument": row.instrument,
        "venue": row.venue,
        "direction": row.direction,
        "quantity": row.quantity,
        "notional": row.notional,
        "leverage": row.leverage,
        "order_type": row.order_type,
        "reduce_only": row.reduce_only,
        "execution_mode": row.execution_mode,
        "status": row.status,
        "approval_status": row.approval_status,
        "expires_at": row.expires_at.isoformat(),
        "confirmation": confirmation,
        "confirmation_required": True,
    }
