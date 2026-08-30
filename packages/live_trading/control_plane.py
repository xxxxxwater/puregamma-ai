"""Trading Control Plane — the ONLY component allowed to submit LIVE orders.

The 23-step execution order enforced here:

 1  user + mandate ownership           12 max leverage
 2  mandate state                      13 max order frequency
 3  LIVE feature flag                  14 kill switches
 4  user LIVE approval                 15 idempotency key
 5  broker connection health           16 persist RiskCheck (immutable)
 6  asset whitelist                    17 persist OrderIntent
 7  quantity/price/notional sanity     18 mandate row lock (txn)
 8  balance check                      19 submit to Execution Gateway
 9  max per-order notional             20 persist broker_order_id
10  total position cap                 21 background fill sync
11  max daily loss                     22 persist Fill + Ledger
                                       23 recompute NAV

Any failure before step 19 means NO order reaches the gateway. After step 19,
failures are recorded (UNKNOWN/REJECTED) and never blindly retried.

Harness / Agent / Memory / Android / iOS / Web / ordinary admin routes can
never call this module directly — only the /api/trading endpoints route into
it after server-side authorization.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import (
    BrokerConnection,
    Fill,
    LiveOrder,
    LiveOrderIntent,
    LiveUserApproval,
    RiskCheck,
    TradingMandate,
    utcnow,
)
from packages.live_trading import audit as audit_service
from packages.live_trading import flags as flags_service
from packages.live_trading import kill_switch as kill_switch_service
from packages.live_trading import ledger as ledger_service
from packages.live_trading import risk_engine
from packages.live_trading import secret_store
from packages.live_trading.enums import (
    IntentStatus,
    LiveOrderStatus,
    MandateStatus,
    OrderSource,
    Side,
)
from packages.live_trading.gateway_adapter import (
    ExecutionGateway,
    GatewayError,
    GatewayOrderUnknown,
    get_execution_gateway,
)

_INTENT_TTL_MINUTES = 10


class ControlPlaneError(RuntimeError):
    pass


class OrderRejected(ControlPlaneError):
    def __init__(self, reason: str, checks: list[dict] | None = None):
        super().__init__(reason)
        self.checks = checks or []


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _decimal(value, default=None) -> Decimal:
    if value is None and default is not None:
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except Exception:
        raise ControlPlaneError(f"Invalid numeric value: {value!r}")


def _new_client_order_id() -> str:
    return f"pg-{uuid.uuid4().hex[:20]}"


def _confirmation_hash(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Mandate + connection helpers
# ---------------------------------------------------------------------------


def owned_mandate(db: Session, user_id: str, mandate_id: str, *, lock: bool = False) -> TradingMandate:
    query = db.query(TradingMandate).filter_by(id=mandate_id, user_id=user_id)
    if lock:
        query = query.with_for_update()
    row = query.one_or_none()
    if not row:
        raise LookupError("Trading mandate not found")
    return row


def owned_connection(db: Session, user_id: str, connection_id: str) -> BrokerConnection:
    row = (
        db.query(BrokerConnection)
        .filter_by(id=connection_id, user_id=user_id)
        .one_or_none()
    )
    if not row:
        raise LookupError("Broker connection not found")
    return row


def _mandate_connection(db: Session, mandate: TradingMandate) -> BrokerConnection | None:
    if not mandate.broker_connection_id:
        return None
    return (
        db.query(BrokerConnection)
        .filter_by(id=mandate.broker_connection_id)
        .one_or_none()
    )


# ---------------------------------------------------------------------------
# Preview / confirm
# ---------------------------------------------------------------------------


def preview_order(
    db: Session,
    user_id: str,
    *,
    mandate_id: str,
    symbol: str,
    side: str,
    quantity: Decimal | str | float,
    order_type: str = "market",
    limit_price: Decimal | str | float | None = None,
    source: str = OrderSource.USER_CONFIRMED.value,
    gateway: ExecutionGateway | None = None,
    trace_id: str | None = None,
) -> dict:
    trace_id = trace_id or audit_service.new_trace_id()
    if source == OrderSource.LIVE_ORDER.value:  # reserved: never accepted
        raise ControlPlaneError("live_order source is reserved and never accepted")
    if source not in {
        OrderSource.USER_CONFIRMED.value,
        OrderSource.STRATEGY.value,
        OrderSource.ADMIN.value,
        OrderSource.SYSTEM.value,
    }:
        raise ControlPlaneError(f"Unsupported order source: {source}")

    mandate = owned_mandate(db, user_id, mandate_id)
    connection = _mandate_connection(db, mandate)
    gate = flags_service.evaluate_full_gate(db, user_id, mandate, connection)
    if not gate.enabled:
        failed = [name for name, value in gate.checks.items() if not value["ok"]]
        raise OrderRejected("LIVE disabled: " + ", ".join(sorted(failed)[:8]))

    ctx = risk_engine.build_ctx(db, mandate=mandate, connection=connection, gateway=gateway)
    verdict = risk_engine.RiskEngine(db).evaluate(
        user_id=user_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=order_type,
        limit_price=limit_price,
        ctx=ctx,
    )
    if verdict.result != "PASS":
        raise OrderRejected(verdict.rejection_reason or "risk rejected", verdict.checks)

    idempotency_key = f"intent:{user_id}:{uuid.uuid4().hex}"
    token = f"CONFIRM LIVE {symbol.upper()} {side.upper()} {quantity} {secrets.token_urlsafe(18)}"
    intent = LiveOrderIntent(
        user_id=user_id,
        mandate_id=mandate.id,
        strategy_release_id=mandate.strategy_release_id,
        broker_connection_id=connection.id if connection else None,
        symbol=symbol.upper(),
        side=str(side).lower(),
        quantity=_decimal(quantity),
        order_type=str(order_type).lower(),
        limit_price=_decimal(limit_price) if limit_price is not None else None,
        client_order_id=_new_client_order_id(),
        idempotency_key=idempotency_key,
        source=source,
        requested_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=_INTENT_TTL_MINUTES),
        status=IntentStatus.PENDING.value,
        confirmation_token_hash=_confirmation_hash(token),
        trace_id=trace_id,
    )
    db.add(intent)
    audit_service.audit(
        db,
        user_id=user_id,
        action="LIVE_ORDER_PREVIEW",
        status="PENDING_CONFIRMATION",
        trace_id=trace_id,
        idempotency_key=f"audit:{idempotency_key}",
        actor_type="user",
        request_json={
            "mandate_id": mandate.id,
            "symbol": symbol.upper(),
            "side": str(side).lower(),
            "quantity": str(quantity),
            "order_type": str(order_type).lower(),
            "source": source,
        },
        result_json={"order_intent_id": intent.id, "risk": verdict.result},
    )
    db.commit()
    db.refresh(intent)
    return {
        "intent": intent,
        "confirmation": token,
        "trace_id": trace_id,
    }


def confirm_order(
    db: Session,
    user_id: str,
    *,
    order_intent_id: str,
    confirmation: str,
    actor_is_admin: bool = False,
    gateway: ExecutionGateway | None = None,
) -> LiveOrder:
    intent = (
        db.query(LiveOrderIntent)
        .filter_by(id=order_intent_id, user_id=user_id)
        .one_or_none()
    )
    if not intent:
        raise LookupError("Order intent not found")

    # Idempotent confirm: an order already exists for this intent -> return it.
    existing_order = (
        db.query(LiveOrder)
        .filter_by(order_intent_id=intent.id, user_id=user_id)
        .one_or_none()
    )
    if existing_order:
        return existing_order

    if intent.status != IntentStatus.PENDING.value:
        raise ControlPlaneError("Order intent is no longer pending")
    expires = _aware(intent.expires_at)
    if expires < datetime.now(timezone.utc):
        intent.status = IntentStatus.EXPIRED.value
        db.commit()
        raise ControlPlaneError("Order confirmation expired")

    if not secrets.compare_digest(
        intent.confirmation_token_hash or "", _confirmation_hash(confirmation)
    ):
        raise ControlPlaneError("Confirmation token does not match the preview")

    # Strategy-sourced suggestions can never be confirmed directly; the user
    # must re-confirm through a user_confirmed intent.
    if intent.source == OrderSource.STRATEGY.value:
        raise ControlPlaneError(
            "Strategy suggestions cannot be confirmed; re-submit as a user-confirmed order"
        )
    if intent.source == OrderSource.ADMIN.value and not actor_is_admin:
        raise ControlPlaneError("Admin-sourced orders require an admin actor")

    # Row lock serializes all operations on this mandate (no concurrent modify).
    mandate = owned_mandate(db, user_id, intent.mandate_id, lock=True)
    connection = _mandate_connection(db, mandate)
    gate = flags_service.evaluate_full_gate(db, user_id, mandate, connection)
    if not gate.enabled:
        failed = [name for name, value in gate.checks.items() if not value["ok"]]
        raise OrderRejected("LIVE disabled: " + ", ".join(sorted(failed)[:8]))

    ctx = risk_engine.build_ctx(
        db, mandate=mandate, connection=connection, gateway=gateway
    )
    verdict = risk_engine.RiskEngine(db).evaluate(
        user_id=user_id,
        symbol=intent.symbol,
        side=intent.side,
        quantity=intent.quantity,
        order_type=intent.order_type,
        limit_price=intent.limit_price,
        ctx=ctx,
    )

    # Step 16: persist the immutable RiskCheck BEFORE anything else.
    risk_check = RiskCheck(
        user_id=user_id,
        order_intent_id=intent.id,
        mandate_id=mandate.id,
        result=verdict.result,
        rejection_reason=verdict.rejection_reason,
        checks_json=verdict.checks,
        checked_at=utcnow(),
        risk_engine_version=risk_engine.RISK_ENGINE_VERSION,
        trace_id=intent.trace_id,
    )
    db.add(risk_check)
    db.flush()

    if verdict.result != "PASS":
        intent.status = IntentStatus.REJECTED.value
        intent.error_code = "RISK_REJECTED"
        intent.error_message = verdict.rejection_reason
        audit_service.audit(
            db,
            user_id=user_id,
            action="LIVE_ORDER_REJECTED_BY_RISK",
            status="REJECTED",
            trace_id=intent.trace_id,
            idempotency_key=f"audit:risk-reject:{intent.id}",
            actor_type="system",
            result_json={"risk_check_id": risk_check.id, "reason": verdict.rejection_reason},
        )
        db.commit()
        raise OrderRejected(verdict.rejection_reason or "risk rejected", verdict.checks)

    # Steps 15 + 17: idempotency key and OrderIntent -> APPROVED.
    order_idempotency = f"order:{intent.idempotency_key}"
    duplicate = (
        db.query(LiveOrder).filter_by(idempotency_key=order_idempotency).one_or_none()
    )
    if duplicate:
        db.rollback()
        return duplicate

    intent.status = IntentStatus.APPROVED.value
    intent.error_code = None
    intent.error_message = None
    order = LiveOrder(
        user_id=user_id,
        mandate_id=mandate.id,
        order_intent_id=intent.id,
        broker_connection_id=connection.id if connection else None,
        symbol=intent.symbol,
        side=intent.side,
        quantity=intent.quantity,
        order_type=intent.order_type,
        limit_price=intent.limit_price,
        status=LiveOrderStatus.PENDING.value,
        client_order_id=intent.client_order_id,
        idempotency_key=order_idempotency,
        trace_id=intent.trace_id,
    )
    db.add(order)
    audit_service.audit(
        db,
        user_id=user_id,
        action="LIVE_ORDER_SUBMIT",
        status="PENDING",
        trace_id=intent.trace_id,
        idempotency_key=f"audit:submit:{intent.id}",
        actor_type="admin" if actor_is_admin else "user",
        result_json={"order_id": order.id},
    )
    db.commit()
    db.refresh(order)

    # Steps 18-20: submit via the Execution Gateway. Failures here NEVER
    # roll back the audit trail; UNKNOWN states are queried, not retried.
    gw = gateway or get_execution_gateway()
    payload = {
        "mode": "live",
        "client_order_id": order.client_order_id,
        "account_id": mandate.account_id,
        "mandate_id": mandate.id,
        "connection_id": connection.id if connection else None,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": str(order.quantity),
        "order_type": order.order_type,
        "limit_price": str(order.limit_price) if order.limit_price is not None else None,
        "idempotency_key": order.idempotency_key,
        "trace_id": intent.trace_id,
        "reduce_only": False,
    }
    try:
        ack = gw.submit_order(payload)
        state = str(ack.get("state") or LiveOrderStatus.UNKNOWN.value).lower()
        if state not in {item.value for item in LiveOrderStatus}:
            state = LiveOrderStatus.UNKNOWN.value
        order.status = state
        order.broker_order_id = ack.get("broker_order_id") or ack.get("exchange_order_id")
        order.submitted_at = utcnow()
        order.last_sync_at = utcnow()
        order.raw_ack_json = ack
        order.error_code = None
        order.error_message = None
        db.commit()
        db.refresh(order)
        # Step 21: background fill sync (fills may already be in the ack).
        _sync_fills_from_ack(db, order, mandate.account_id, ack)
        db.commit()
        _trigger_nav_update(order.user_id, mandate.account_id, order.mandate_id)
        return order
    except GatewayOrderUnknown as exc:
        # Submit timed out or transport failed: state is UNKNOWN. Never blind
        # retry; record and let the status-sync task query the gateway.
        order.status = LiveOrderStatus.UNKNOWN.value
        order.error_code = "SUBMIT_UNKNOWN"
        order.error_message = str(exc)[:300]
        order.submitted_at = utcnow()
        order.last_sync_at = utcnow()
        audit_service.audit(
            db,
            user_id=user_id,
            action="LIVE_ORDER_SUBMIT_UNKNOWN",
            status="UNKNOWN",
            trace_id=intent.trace_id,
            idempotency_key=f"audit:unknown:{order.id}",
            actor_type="system",
            error=str(exc)[:300],
        )
        db.commit()
        db.refresh(order)
        return order
    except GatewayError as exc:
        order.status = LiveOrderStatus.REJECTED.value
        order.error_code = "GATEWAY_UNAVAILABLE"
        order.error_message = str(exc)[:300]
        order.submitted_at = utcnow()
        order.last_sync_at = utcnow()
        db.commit()
        db.refresh(order)
        return order


# ---------------------------------------------------------------------------
# Fills + ledger + NAV
# ---------------------------------------------------------------------------


def _sync_fills_from_ack(
    db: Session, order: LiveOrder, account_id: str, ack: dict
) -> None:
    fills = ack.get("fills") or []
    for fill in fills:
        _apply_fill(
            db,
            order,
            account_id=account_id,
            broker_fill_id=str(fill.get("broker_fill_id") or fill.get("fill_id") or uuid.uuid4()),
            quantity=Decimal(str(fill.get("quantity", order.quantity))),
            price=Decimal(str(fill.get("price") or fill.get("average_price") or 0)),
            fee=Decimal(str(fill.get("fee") or 0)),
            fee_currency=str(fill.get("fee_currency") or "USD"),
            executed_at=_aware(_parse_dt(fill.get("executed_at"))),
            raw=fill,
        )


def _parse_dt(value):
    if value is None:
        return utcnow()
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return utcnow()


def _apply_fill(
    db: Session,
    order: LiveOrder,
    *,
    account_id: str,
    broker_fill_id: str,
    quantity: Decimal,
    price: Decimal,
    fee: Decimal,
    fee_currency: str,
    executed_at: datetime,
    raw: dict,
) -> Fill:
    existing = (
        db.query(Fill).filter_by(broker_fill_id=broker_fill_id).one_or_none()
    )
    if existing:
        return existing

    fill = Fill(
        user_id=order.user_id,
        order_id=order.id,
        mandate_id=order.mandate_id,
        symbol=order.symbol,
        side=order.side,
        quantity=quantity,
        price=price,
        fee=fee,
        fee_currency=fee_currency,
        executed_at=executed_at,
        broker_fill_id=broker_fill_id,
        raw_reference_json=raw,
    )
    db.add(fill)
    db.flush()

    notional = quantity * price
    if order.side == Side.BUY.value:
        cash_delta = -notional - fee
        entry_type = "trade_buy"
    else:
        cash_delta = notional - fee
        entry_type = "trade_sell"
    signed_qty = quantity if order.side == Side.BUY.value else -quantity

    ledger_service.post_entry(
        db,
        user_id=order.user_id,
        account_id=account_id,
        mandate_id=order.mandate_id,
        entry_type=entry_type,
        amount=cash_delta,
        ref_type="fill",
        ref_id=fill.id,
        symbol=order.symbol,
        quantity=signed_qty,
        price=price,
        idempotency_key=f"ledger:{fill.id}",
        trace_id=order.trace_id,
    )
    if fee > 0:
        ledger_service.post_entry(
            db,
            user_id=order.user_id,
            account_id=account_id,
            mandate_id=order.mandate_id,
            entry_type="fee",
            amount=-fee,
            currency=fee_currency,
            ref_type="fill",
            ref_id=fill.id,
            idempotency_key=f"ledger:fee:{fill.id}",
            trace_id=order.trace_id,
        )

    filled = _decimal(order.filled_quantity or 0) + quantity
    order.filled_quantity = filled
    order.average_price = (
        ((_decimal(order.average_price or 0) * _decimal(order.filled_quantity or 0)) + notional)
        / filled
        if filled > 0
        else price
    )
    total = _decimal(order.quantity)
    if filled >= total:
        order.status = LiveOrderStatus.FILLED.value
    elif filled > 0:
        order.status = LiveOrderStatus.PARTIALLY_FILLED.value
    order.last_sync_at = utcnow()
    db.flush()
    return fill


def sync_order_status(db: Session, order: LiveOrder, gateway: ExecutionGateway | None = None) -> LiveOrder:
    """Background order-state sync. UNKNOWN states are resolved by QUERYING
    the gateway — never by re-submitting."""
    if order.status in {
        LiveOrderStatus.FILLED.value,
        LiveOrderStatus.CANCELED.value,
        LiveOrderStatus.REJECTED.value,
        LiveOrderStatus.EXPIRED.value,
    }:
        return order
    mandate = db.query(TradingMandate).filter_by(id=order.mandate_id).one_or_none()
    account_id = mandate.account_id if mandate else ""
    connection_id = mandate.broker_connection_id if mandate else None
    gw = gateway or get_execution_gateway()
    try:
        result = gw.query_order(
            order.client_order_id,
            account_id,
            connection_id=connection_id,
            symbol=order.symbol,
        )
        state = str(result.get("state") or LiveOrderStatus.UNKNOWN.value).lower()
        if state in {item.value for item in LiveOrderStatus}:
            order.status = state
        order.last_sync_at = utcnow()
        broker = result.get("order") or {}
        if broker.get("broker_order_id") or broker.get("exchange_order_id"):
            order.broker_order_id = broker.get("broker_order_id") or broker.get("exchange_order_id")
        _sync_fills_from_ack(db, order, account_id, {"fills": broker.get("fills") or []})
    except (GatewayError, GatewayOrderUnknown):
        # Keep last known state; UNKNOWN stays UNKNOWN until gateway answers.
        order.last_sync_at = utcnow()
    db.commit()
    _trigger_nav_update(order.user_id, account_id, order.mandate_id)
    return order


def _trigger_nav_update(user_id: str, account_id: str, mandate_id: str | None) -> None:
    """NAV recalculation is only meaningful while LIVE trading is enabled;
    the gate also keeps unit tests from touching the Celery broker."""
    try:
        from apps.api.config import get_settings

        if not get_settings().live_trading_enabled:
            return
        from packages.workers.tasks import calc_nav_for_account

        calc_nav_for_account.delay(user_id, account_id, mandate_id)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def cancel_order(
    db: Session,
    user_id: str,
    client_order_id: str,
    *,
    gateway: ExecutionGateway | None = None,
) -> LiveOrder:
    """Cancellation stays allowed even when kill switches are engaged."""
    order = (
        db.query(LiveOrder)
        .filter_by(client_order_id=client_order_id, user_id=user_id)
        .order_by(LiveOrder.created_at.desc())
        .first()
    )
    if not order:
        raise LookupError("Order not found")
    if order.status in {
        LiveOrderStatus.FILLED.value,
        LiveOrderStatus.CANCELED.value,
        LiveOrderStatus.REJECTED.value,
        LiveOrderStatus.EXPIRED.value,
    }:
        return order
    mandate = (
        db.query(TradingMandate).filter_by(id=order.mandate_id).one_or_none()
    )
    if not mandate:
        raise LookupError("Mandate not found")
    gw = gateway or get_execution_gateway()
    try:
        ack = gw.cancel_order(
            order.client_order_id,
            mandate.account_id,
            connection_id=mandate.broker_connection_id,
            symbol=order.symbol,
        )
        state = str(ack.get("state") or LiveOrderStatus.CANCELED.value).lower()
        if state in {item.value for item in LiveOrderStatus}:
            order.status = state
    except GatewayError as exc:
        order.error_code = "CANCEL_UNKNOWN"
        order.error_message = str(exc)[:300]
    order.last_sync_at = utcnow()
    audit_service.audit(
        db,
        user_id=user_id,
        action="LIVE_ORDER_CANCEL",
        status=order.status,
        trace_id=order.trace_id,
        idempotency_key=f"audit:cancel:{order.id}",
        actor_type="user",
        result_json={"order_id": order.id},
    )
    db.commit()
    db.refresh(order)
    return order


# ---------------------------------------------------------------------------
# Pause / resume (resume requires a human action + full gate re-check)
# ---------------------------------------------------------------------------


def pause_mandate(
    db: Session,
    user_id: str,
    mandate_id: str,
    *,
    reason: str,
    actor_is_admin: bool = False,
) -> TradingMandate:
    mandate = owned_mandate(db, user_id, mandate_id, lock=True)
    if not actor_is_admin and mandate.paused:
        return mandate
    mandate.paused = True
    mandate.pause_reason = reason[:2000]
    audit_service.audit(
        db,
        user_id=user_id,
        action="LIVE_MANDATE_PAUSE",
        status="PAUSED",
        trace_id=audit_service.new_trace_id(),
        idempotency_key=f"audit:pause:{mandate.id}:{int(utcnow().timestamp())}",
        actor_type="admin" if actor_is_admin else "user",
        result_json={"mandate_id": mandate.id, "reason": reason},
    )
    db.commit()
    db.refresh(mandate)
    return mandate


def resume_mandate(
    db: Session,
    user_id: str,
    mandate_id: str,
    *,
    confirmation: str,
    gateway: ExecutionGateway | None = None,
) -> TradingMandate:
    mandate = owned_mandate(db, user_id, mandate_id, lock=True)
    if not mandate.paused:
        return mandate
    expected = f"RESUME {mandate.id}"
    if not secrets.compare_digest(confirmation, expected):
        raise ControlPlaneError("Resume confirmation phrase does not match")
    # Auto-pauses triggered by risk/reconciliation require admin resolution.
    if mandate.pause_reason and mandate.pause_reason.startswith("reconciliation"):
        raise ControlPlaneError(
            "This pause was triggered by reconciliation; resume requires admin resolution"
        )
    if kill_switch_service.is_engaged(db, "mandate", mandate.id) or kill_switch_service.is_engaged(
        db, "global"
    ):
        raise ControlPlaneError("A kill switch is engaged; resume requires admin resolution")
    gate = flags_service.evaluate_full_gate(
        db, user_id, mandate, _mandate_connection(db, mandate)
    )
    if not gate.enabled:
        failed = [name for name, value in gate.checks.items() if not value["ok"]]
        raise ControlPlaneError("LIVE gates not satisfied: " + ", ".join(sorted(failed)[:8]))
    mandate.paused = False
    mandate.pause_reason = None
    mandate.status = MandateStatus.ACTIVE.value
    audit_service.audit(
        db,
        user_id=user_id,
        action="LIVE_MANDATE_RESUME",
        status="RESUMED",
        trace_id=audit_service.new_trace_id(),
        idempotency_key=f"audit:resume:{mandate.id}:{int(utcnow().timestamp())}",
        actor_type="user",
        result_json={"mandate_id": mandate.id},
    )
    db.commit()
    db.refresh(mandate)
    return mandate


# ---------------------------------------------------------------------------
# Queries + safety status
# ---------------------------------------------------------------------------


def list_mandates(db: Session, user_id: str) -> list[dict]:
    rows = (
        db.query(TradingMandate)
        .filter_by(user_id=user_id)
        .order_by(TradingMandate.created_at.desc())
        .all()
    )
    return [_serialize_mandate(row) for row in rows]


def get_mandate(db: Session, user_id: str, mandate_id: str) -> dict:
    return _serialize_mandate(owned_mandate(db, user_id, mandate_id))


def _serialize_mandate(row: TradingMandate) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "account_id": row.account_id,
        "strategy_release_id": row.strategy_release_id,
        "broker_connection_id": row.broker_connection_id,
        "execution_mode": row.execution_mode,
        "environment": row.environment,
        "status": row.status,
        "allowed_symbols": row.allowed_symbols_json or [],
        "allowed_side": row.allowed_side,
        "max_total_notional": str(row.max_total_notional),
        "max_per_order_notional": str(row.max_per_order_notional),
        "max_position_notional": str(row.max_position_notional),
        "max_leverage": str(row.max_leverage),
        "max_daily_loss": str(row.max_daily_loss),
        "max_trades_per_day": row.max_trades_per_day,
        "max_order_frequency_seconds": row.max_order_frequency_seconds,
        "kill_switch_state": row.kill_switch_state,
        "paused": row.paused,
        "pause_reason": row.pause_reason,
        "approval_status": row.approval_status,
        "approved_by": row.approved_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "created_at": row.created_at.isoformat(),
    }


def list_orders(db: Session, user_id: str, *, mandate_id: str | None = None) -> list[dict]:
    query = db.query(LiveOrder).filter_by(user_id=user_id)
    if mandate_id:
        query = query.filter_by(mandate_id=mandate_id)
    rows = query.order_by(LiveOrder.created_at.desc()).limit(300).all()
    return [_serialize_order(row) for row in rows]


def get_order(db: Session, user_id: str, order_id: str) -> dict:
    row = db.query(LiveOrder).filter_by(id=order_id, user_id=user_id).one_or_none()
    if not row:
        raise LookupError("Order not found")
    return _serialize_order(row)


def _serialize_order(row: LiveOrder) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "mandate_id": row.mandate_id,
        "order_intent_id": row.order_intent_id,
        "symbol": row.symbol,
        "side": row.side,
        "quantity": str(row.quantity),
        "order_type": row.order_type,
        "limit_price": str(row.limit_price) if row.limit_price is not None else None,
        "status": row.status,
        "client_order_id": row.client_order_id,
        "broker_order_id": row.broker_order_id,
        "filled_quantity": str(row.filled_quantity or 0),
        "average_price": str(row.average_price) if row.average_price is not None else None,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat(),
    }


def _serialize_connection(row: BrokerConnection) -> dict:
    return {
        "id": row.id,
        "provider": row.provider,
        "account_label": row.account_label,
        "environment": row.environment,
        "status": row.status,
        "permissions": row.permissions_json,
        "has_credentials": bool(row.encrypted_credentials_ref),
        "last_health_check_at": row.last_health_check_at.isoformat()
        if row.last_health_check_at
        else None,
        "error_code": row.error_code,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "created_at": row.created_at.isoformat(),
    }


def list_connections(db: Session, user_id: str) -> list[dict]:
    rows = (
        db.query(BrokerConnection)
        .filter_by(user_id=user_id)
        .order_by(BrokerConnection.created_at.desc())
        .all()
    )
    return [_serialize_connection(row) for row in rows]


def test_connection(
    db: Session, user_id: str, connection_id: str, gateway: ExecutionGateway | None = None
) -> dict:
    """Health test only; credentials are never echoed back.

    - a DISABLED gateway is reported honestly as DISCONNECTED (mock semantics);
    - an API key whose permissions allow withdrawal/transfer/leverage/futures/
      options is hard-rejected (status ERROR + UNSAFE_API_PERMISSIONS) and an
      ops alert is raised — the connection can never trade;
    - network/credential failures mark ERROR and surface the reason.
    """
    connection = owned_connection(db, user_id, connection_id)
    if connection.revoked_at:
        raise ControlPlaneError("Connection is revoked")
    gw = gateway or get_execution_gateway()
    try:
        health = gw.health(connection_id=connection.id)
    except GatewayError as exc:
        connection.status = "ERROR"
        connection.error_code = "HEALTH_CHECK_FAILED"
        connection.error_message = str(exc)[:300]
        connection.last_health_check_at = utcnow()
        db.commit()
        raise ControlPlaneError(f"Connection health check failed: {exc}") from exc

    if health.get("status") == "DISABLED":
        # Honest mock semantics: the gateway refuses execution; the connection
        # is not unhealthy, it simply cannot trade yet.
        connection.status = "DISCONNECTED"
        connection.error_code = "GATEWAY_DISABLED"
        connection.error_message = "Execution gateway is disabled; no real venue is reachable"
        connection.last_health_check_at = utcnow()
        db.commit()
        return {"status": connection.status, "health": health}

    permissions = health.get("permissions") or {}
    if permissions.get("safe") is False:
        connection.status = "ERROR"
        connection.error_code = "UNSAFE_API_PERMISSIONS"
        connection.error_message = "; ".join(
            permissions.get("unsafe_permissions") or ["unknown"]
        )[:300]
        connection.last_health_check_at = utcnow()
        db.commit()
        _notify_ops(
            user_id,
            connection_id,
            "broker API key permissions are unsafe; connection rejected "
            f"({connection.error_message})",
        )
        raise ControlPlaneError(
            "Broker API key permissions are unsafe: "
            + (connection.error_message or "withdrawal/transfer/leverage enabled")
        )

    connection.status = "HEALTHY" if health.get("status") in {"HEALTHY", "CONNECTED"} else "ERROR"
    connection.last_health_check_at = utcnow()
    connection.error_code = None
    connection.error_message = None
    db.commit()
    return {"status": connection.status, "health": health}


def bind_connection(
    db: Session,
    user_id: str,
    *,
    provider: str,
    account_label: str,
    credentials: dict,
    environment: str = "production",
    gateway: ExecutionGateway | None = None,
) -> BrokerConnection:
    """User self-service exchange API key binding.

    Credentials are Fernet-encrypted before they ever touch the database, the
    provider must be the one the deployment has provisioned, and the key is
    immediately health/permission-verified — an unsafe key (withdrawal,
    transfer, leverage, futures, options) is stored but marked ERROR and the
    bind call fails closed. Plaintext is never returned to the caller.
    """
    settings = get_settings()
    if not settings.live_trading_provider:
        raise ControlPlaneError(
            "Live trading provider is not configured on this deployment"
        )
    if settings.live_trading_provider and provider != settings.live_trading_provider:
        raise ControlPlaneError(
            f"Provider '{provider}' is not enabled by this deployment"
        )
    if environment != "production":
        raise ControlPlaneError("Self-service binding is production-only in this release")
    api_key = str(credentials.get("api_key") or "").strip()
    api_secret = str(credentials.get("api_secret") or "").strip()
    if not api_key or not api_secret:
        raise ControlPlaneError("api_key and api_secret are required credentials")
    active = (
        db.query(BrokerConnection)
        .filter_by(user_id=user_id)
        .filter(BrokerConnection.revoked_at.is_(None))
        .count()
    )
    if active >= 3:
        raise ControlPlaneError("Connection limit reached (max 3 active connections)")
    existing = (
        db.query(BrokerConnection)
        .filter_by(user_id=user_id, provider=provider, account_label=account_label)
        .one_or_none()
    )
    if existing:
        raise ControlPlaneError("Connection label already exists")

    trace_id = audit_service.new_trace_id()
    row = BrokerConnection(
        user_id=user_id,
        provider=provider,
        account_label=account_label[:128],
        encrypted_credentials_ref=secret_store.encrypt_secrets(
            {"api_key": api_key, "api_secret": api_secret}
        ),
        permissions_json={
            "spot": True,
            "margin": False,
            "futures": False,
            "options": False,
            "shorting": False,
            "withdraw": False,
            "transfer": False,
        },
        environment=environment,
        status="DISCONNECTED",
    )
    db.add(row)
    # Flush so the ORM default assigns row.id before it is embedded in the
    # audit idempotency key — otherwise every first bind logs
    # "audit:bind:None" and later binds silently skip their audit entry.
    db.flush()
    audit_service.audit(
        db,
        user_id=user_id,
        action="LIVE_CONNECTION_BOUND",
        status="DISCONNECTED",
        trace_id=trace_id,
        idempotency_key=f"audit:bind:{row.id}",
        actor_type="user",
        result_json={"provider": provider, "account_label": account_label},
    )
    db.commit()
    db.refresh(row)
    # Immediate verification: health + API-key permission hard-check.
    try:
        test_connection(db, user_id, row.id, gateway=gateway)
    except ControlPlaneError as exc:
        raise ControlPlaneError(f"Connection rejected: {exc}") from exc
    return row


def revoke_connection(
    db: Session, user_id: str, connection_id: str
) -> BrokerConnection:
    """Self-service revoke. Also pauses every LIVE mandate bound to it."""
    connection = owned_connection(db, user_id, connection_id)
    if connection.revoked_at:
        return connection
    connection.revoked_at = utcnow()
    connection.revoked_by = user_id
    connection.status = "REVOKED"
    trace_id = audit_service.new_trace_id()
    paused = []
    for mandate in (
        db.query(TradingMandate)
        .filter_by(user_id=user_id, broker_connection_id=connection.id)
        .all()
    ):
        if mandate.execution_mode != "live" or mandate.paused:
            continue
        mandate.paused = True
        mandate.pause_reason = "connection_revoked"
        paused.append(mandate.id)
    audit_service.audit(
        db,
        user_id=user_id,
        action="LIVE_CONNECTION_REVOKED",
        status="REVOKED",
        trace_id=trace_id,
        idempotency_key=f"audit:revoke:{connection.id}",
        actor_type="user",
        result_json={"paused_mandates": paused},
    )
    db.commit()
    db.refresh(connection)
    return connection


def _notify_ops(user_id: str, connection_id: str, message: str) -> None:
    try:
        from apps.api.services.ops_alert import notify_ops

        notify_ops(f"[live-trading] user={user_id} connection={connection_id} {message}")
    except Exception:
        pass


def safety_status(db: Session, user_id: str) -> dict:
    """User-facing safety view: gate conditions, mandates, kill switches."""
    static = flags_service.evaluate_static_gate()
    approval = db.query(LiveUserApproval).filter_by(user_id=user_id).one_or_none()
    mandates = (
        db.query(TradingMandate).filter_by(user_id=user_id).all()
    )
    mandate_gates = {}
    for mandate in mandates:
        gate = flags_service.evaluate_full_gate(
            db, user_id, mandate, _mandate_connection(db, mandate)
        )
        mandate_gates[mandate.id] = gate.as_dict()
    return {
        "static_gate": static.as_dict(),
        "user_live_approval": {
            "status": approval.status if approval else "none",
            "max_total_notional": str(approval.max_total_notional) if approval else "0",
            "reviewed_at": approval.reviewed_at.isoformat() if approval and approval.reviewed_at else None,
        },
        "mandates": mandate_gates,
        "kill_switches": kill_switch_service.active_switches(db, user_id),
    }


def list_fills(db: Session, user_id: str, *, order_id: str | None = None) -> list[dict]:
    query = db.query(Fill).filter_by(user_id=user_id)
    if order_id:
        query = query.filter_by(order_id=order_id)
    rows = query.order_by(Fill.executed_at.desc()).limit(500).all()
    return [
        {
            "id": row.id,
            "order_id": row.order_id,
            "symbol": row.symbol,
            "side": row.side,
            "quantity": str(row.quantity),
            "price": str(row.price),
            "fee": str(row.fee),
            "fee_currency": row.fee_currency,
            "executed_at": row.executed_at.isoformat() if row.executed_at else None,
            "broker_fill_id": row.broker_fill_id,
        }
        for row in rows
    ]
