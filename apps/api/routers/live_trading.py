"""LIVE trading + NAV HTTP surface.

Two routers are exported:

- ``trading_router`` (prefix ``/api/trading``): connections, mandates,
  order preview/confirm/cancel, pause/resume, safety status.
- ``portfolio_router`` (prefix ``/api/portfolio``): server-computed NAV,
  NAV history and derived positions.

Every LIVE order flows through the Trading Control Plane; mobile/web clients
can never reach a broker directly. All numeric risk values travel as strings
(Decimal) so no binary float ever leaks into risk math.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db, require_admin
from packages.database.models import TradingAccount, User
from packages.live_trading import control_plane, nav as nav_service, ledger as ledger_service
from packages.live_trading import price_feed as price_feed_service
from packages.live_trading.control_plane import ControlPlaneError, OrderRejected
from packages.live_trading.enums import OrderSource
from packages.live_trading.gateway_adapter import GatewayError
from packages.live_trading.secret_store import SecretStoreError

trading_router = APIRouter(prefix="/api/trading", tags=["live-trading"])
portfolio_router = APIRouter(prefix="/api/portfolio", tags=["live-portfolio"])


class LiveOrderPreviewRequest(BaseModel):
    mandate_id: str
    symbol: str = Field(min_length=1, max_length=32)
    side: str = Field(pattern="^(buy|sell)$")
    quantity: str = Field(pattern=r"^\d+(\.\d+)?$")
    order_type: str = Field(default="market", pattern="^(market|limit)$")
    limit_price: str | None = Field(default=None, pattern=r"^\d+(\.\d+)?$")
    source: str = Field(default=OrderSource.USER_CONFIRMED.value)


class LiveOrderConfirmRequest(BaseModel):
    order_intent_id: str
    confirmation: str = Field(min_length=16, max_length=500)


class LiveOrderCancelRequest(BaseModel):
    client_order_id: str


class MandatePauseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class MandateResumeRequest(BaseModel):
    confirmation: str = Field(min_length=8, max_length=500)


class ConnectionTestRequest(BaseModel):
    connection_id: str


class ConnectionBindRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    account_label: str = Field(min_length=1, max_length=128)
    credentials: dict = Field(default_factory=dict)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, OrderRejected):
        return HTTPException(
            status_code=400,
            detail={"code": "ORDER_REJECTED", "message": str(exc), "checks": exc.checks},
        )
    if isinstance(exc, (ControlPlaneError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, GatewayError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, SecretStoreError):
        return HTTPException(status_code=500, detail="Credential store unavailable")
    return HTTPException(status_code=500, detail="Trading control failed")


def _serialize_nav(row) -> dict:
    return {
        "id": row.id,
        "account_id": row.account_id,
        "nav": str(row.nav) if row.nav is not None else None,
        "cash": str(row.cash),
        "gross_exposure": str(row.gross_exposure),
        "net_exposure": str(row.net_exposure),
        "realized_pnl": str(row.realized_pnl),
        "unrealized_pnl": str(row.unrealized_pnl),
        "currency": row.currency,
        "price_timestamp": row.price_timestamp.isoformat() if row.price_timestamp else None,
        "calculated_at": row.calculated_at.isoformat(),
        "is_stale": row.is_stale,
        "calculation_version": row.calculation_version,
        "reconciliation_status": row.reconciliation_status,
    }


def _owned_account(db: Session, user_id: str, account_id: str) -> TradingAccount:
    row = (
        db.query(TradingAccount).filter_by(id=account_id, user_id=user_id).one_or_none()
    )
    if not row:
        raise LookupError("Trading account not found")
    return row


def _default_account(db: Session, user_id: str) -> TradingAccount:
    row = (
        db.query(TradingAccount)
        .filter_by(user_id=user_id, status="ACTIVE")
        .order_by(TradingAccount.created_at)
        .first()
    )
    if not row:
        raise LookupError("No active trading account")
    return row


# ---------------------------------------------------------------------------
# /api/trading/connections
# ---------------------------------------------------------------------------


@trading_router.get("/connections")
def list_connections(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return {"connections": control_plane.list_connections(db, user.id)}


@trading_router.post("/connections")
def bind_connection(
    payload: ConnectionBindRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Self-service exchange API key binding.

    Credentials are Fernet-encrypted server-side (plaintext is never persisted
    nor echoed back) and the key is immediately health/permission-verified.
    An unsafe key (withdrawal/transfer/leverage/futures/options enabled) is
    rejected with a 400 and the stored connection is marked ERROR.
    """
    try:
        connection = control_plane.bind_connection(
            db,
            user.id,
            provider=payload.provider,
            account_label=payload.account_label,
            credentials=payload.credentials,
        )
        return {"connection": control_plane._serialize_connection(connection)}
    except Exception as exc:
        raise _http_error(exc) from exc


@trading_router.post("/connections/{connection_id}/revoke")
def revoke_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        connection = control_plane.revoke_connection(db, user.id, connection_id)
        return {"connection": control_plane._serialize_connection(connection)}
    except Exception as exc:
        raise _http_error(exc) from exc


@trading_router.post("/connections/test")
def test_connection(
    payload: ConnectionTestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return {"health": control_plane.test_connection(db, user.id, payload.connection_id)}
    except Exception as exc:
        raise _http_error(exc) from exc


# ---------------------------------------------------------------------------
# /api/trading/mandates
# ---------------------------------------------------------------------------


@trading_router.get("/mandates")
def list_mandates(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return {"mandates": control_plane.list_mandates(db, user.id)}


@trading_router.get("/mandates/{mandate_id}")
def get_mandate(
    mandate_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return {"mandate": control_plane.get_mandate(db, user.id, mandate_id)}
    except Exception as exc:
        raise _http_error(exc) from exc


@trading_router.post("/mandates/{mandate_id}/pause")
def pause_mandate(
    mandate_id: str,
    payload: MandatePauseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        mandate = control_plane.pause_mandate(
            db, user.id, mandate_id, reason=payload.reason
        )
        return {"mandate": control_plane._serialize_mandate(mandate)}
    except Exception as exc:
        raise _http_error(exc) from exc


@trading_router.post("/mandates/{mandate_id}/resume")
def resume_mandate(
    mandate_id: str,
    payload: MandateResumeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        mandate = control_plane.resume_mandate(
            db, user.id, mandate_id, confirmation=payload.confirmation
        )
        return {"mandate": control_plane._serialize_mandate(mandate)}
    except Exception as exc:
        raise _http_error(exc) from exc


# ---------------------------------------------------------------------------
# /api/trading/orders
# ---------------------------------------------------------------------------


@trading_router.get("/orders")
def list_orders(
    mandate_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return {"orders": control_plane.list_orders(db, user.id, mandate_id=mandate_id)}


@trading_router.get("/orders/{order_id}")
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return {"order": control_plane.get_order(db, user.id, order_id)}
    except Exception as exc:
        raise _http_error(exc) from exc


@trading_router.get("/fills")
def list_fills(
    order_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return {"fills": control_plane.list_fills(db, user.id, order_id=order_id)}


@trading_router.post("/orders/preview")
def order_preview(
    payload: LiveOrderPreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        result = control_plane.preview_order(
            db,
            user.id,
            mandate_id=payload.mandate_id,
            symbol=payload.symbol,
            side=payload.side,
            quantity=payload.quantity,
            order_type=payload.order_type,
            limit_price=payload.limit_price,
            source=payload.source,
        )
        intent = result["intent"]
        return {
            "intent": {
                "id": intent.id,
                "mandate_id": intent.mandate_id,
                "symbol": intent.symbol,
                "side": intent.side,
                "quantity": str(intent.quantity),
                "order_type": intent.order_type,
                "limit_price": str(intent.limit_price) if intent.limit_price is not None else None,
                "source": intent.source,
                "status": intent.status,
                "requested_at": intent.requested_at.isoformat(),
                "expires_at": intent.expires_at.isoformat(),
                "confirmation_required": True,
            },
            "confirmation": result["confirmation"],
            "trace_id": result["trace_id"],
        }
    except Exception as exc:
        raise _http_error(exc) from exc


@trading_router.post("/orders/confirm")
def order_confirm(
    payload: LiveOrderConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        order = control_plane.confirm_order(
            db,
            user.id,
            order_intent_id=payload.order_intent_id,
            confirmation=payload.confirmation,
            actor_is_admin=user.role == "admin",
        )
        return {"order": control_plane._serialize_order(order)}
    except Exception as exc:
        raise _http_error(exc) from exc


@trading_router.post("/orders/cancel")
def order_cancel(
    payload: LiveOrderCancelRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        order = control_plane.cancel_order(db, user.id, payload.client_order_id)
        return {"order": control_plane._serialize_order(order)}
    except Exception as exc:
        raise _http_error(exc) from exc


@trading_router.get("/safety-status")
def safety_status(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return {"safety": control_plane.safety_status(db, user.id)}


# ---------------------------------------------------------------------------
# /api/portfolio (NAV is computed server-side only)
# ---------------------------------------------------------------------------


@portfolio_router.get("/nav")
def current_nav(
    account_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    account = (
        _owned_account(db, user.id, account_id) if account_id else _default_account(db, user.id)
    )
    snapshot = nav_service.latest_snapshot(db, user.id, account.id)
    if not snapshot:
        # Compute one on demand rather than fabricate; prices may be missing.
        snapshot = nav_service.calculate_nav(
            db, user_id=user.id, account_id=account.id
        )
        db.commit()
    history = nav_service.history(db, user.id, account.id, limit=2)
    daily_pnl = None
    daily_return = None
    if snapshot.nav is not None and len(history) >= 2:
        previous = history[1]
        if previous.nav is not None:
            daily_pnl = str(snapshot.nav - previous.nav)
            if previous.nav != 0:
                daily_return = str(
                    (snapshot.nav - previous.nav) / previous.nav
                )
    return {
        "nav": _serialize_nav(snapshot),
        "daily_pnl": daily_pnl,
        "daily_return": daily_return,
    }


@portfolio_router.get("/nav/history")
def nav_history(
    account_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    account = (
        _owned_account(db, user.id, account_id) if account_id else _default_account(db, user.id)
    )
    rows = nav_service.history(db, user.id, account.id, limit=limit)
    return {"history": [_serialize_nav(row) for row in rows]}


@portfolio_router.get("/positions")
def positions(
    account_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    account = (
        _owned_account(db, user.id, account_id) if account_id else _default_account(db, user.id)
    )
    quantities = ledger_service.position_quantities(db, account.id)
    rows = []
    for symbol, qty in sorted(quantities.items()):
        if qty == 0:
            continue
        price, price_at = price_feed_service.latest_valid_price(db, symbol)
        stale = price is None
        rows.append(
            {
                "symbol": symbol,
                "quantity": str(qty),
                "mark_price": str(price) if price is not None else None,
                "market_value": str(qty * price) if price is not None else None,
                "price_timestamp": price_at.isoformat() if price_at else None,
                "stale": stale,
            }
        )
    return {"positions": rows}
