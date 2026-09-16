"""Private, read-only view of the independent riskbot Portfolio Margin snapshot.

Never uses Binance credentials, never accepts a user-supplied upstream URL, and
never exposes this account through the shared portfolio aggregation or Agent.
The bridge is intentionally disabled until the private runtime configuration
and the independent riskbot snapshot exporter are both in place.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests
from fastapi import APIRouter, Depends, HTTPException, Response

from apps.api.dependencies import get_current_user
from packages.database.models import User

router = APIRouter(prefix="/portfolio/private-pm", tags=["private-pm"])

ACCOUNT_FIELDS = (
    "account_status", "uni_mmr", "account_equity_usd", "actual_equity_usd",
    "available_usd", "initial_margin_usd", "maintenance_margin_usd",
    "max_withdraw_usd", "wallet_balance_usd", "unrealized_pnl_usd",
    "btc_usdt_mark", "equity_btc_equivalent", "available_btc_equivalent",
    "gross_notional_usd", "net_notional_usd", "gross_notional_btc_equivalent",
    "net_notional_btc_equivalent", "gross_leverage_estimate",
    "maintenance_to_equity_estimate", "drawdown_btc_day", "drawdown_btc_hwm",
)
BALANCE_FIELDS = ("asset", "wallet_balance", "borrowed", "interest", "unrealized_pnl", "btc_equivalent", "usd_equivalent", "price_source")
POSITION_FIELDS = ("product", "symbol", "side", "position_side", "quantity", "quantity_unit", "entry_price", "mark_price", "notional_usd", "notional_btc_equivalent", "unrealized_pnl", "liquidation_price", "leverage", "update_time_ms", "protection_status")
ORDER_FIELDS = ("product", "kind", "symbol", "order_id", "client_order_id", "side", "position_side", "order_type", "status", "quantity", "executed_quantity", "price", "trigger_price", "reduce_only", "close_position", "created_time_ms", "updated_time_ms")
COVERAGE_FIELDS = ("account", "balance", "um_positions", "cm_positions", "um_orders", "um_algo_orders", "cm_orders", "cm_conditional_orders", "margin_orders", "margin_oco_orders")


def _allowed_user(user: User) -> bool:
    """The deployment MUST configure exactly the two intended verified users."""
    values = [item.strip().casefold() for item in os.getenv("RISKBOT_PM_ALLOWED_EMAILS", "").split(",") if item.strip()]
    return (len(values) == 2 and len(set(values)) == 2
            and user.email_verified_at is not None
            and user.auth_provider != "mock"
            and str(user.email).strip().casefold() in values)


def _safe_url() -> str:
    value = os.getenv("RISKBOT_PM_SNAPSHOT_URL", "").strip()
    parsed = urlsplit(value)
    # This is deployment-owned configuration, not a request argument. Never
    # follow redirects or send service credentials to an arbitrary host.
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(status_code=503, detail={"code": "PM_BRIDGE_UNCONFIGURED"})
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "riskbot", "riskbot-riskbot-1"}:
        raise HTTPException(status_code=503, detail={"code": "PM_BRIDGE_INSECURE_UPSTREAM"})
    if parsed.path != "/v1/portfolio/snapshot":
        raise HTTPException(status_code=503, detail={"code": "PM_BRIDGE_INVALID_ENDPOINT"})
    return value


def _pick(value: object, names: tuple[str, ...]) -> dict:
    if not isinstance(value, dict):
        return {}
    return {name: value[name] for name in names if name in value and value[name] is not None}


def _snapshot(payload: object) -> dict:
    """Strict output projection: exchange raw JSON and API keys never cross."""
    if not isinstance(payload, dict) or payload.get("source") != "binance_pm_classic":
        raise HTTPException(status_code=503, detail={"code": "PM_INVALID_SNAPSHOT"})
    raw_time = payload.get("captured_at")
    try:
        captured = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        if captured.tzinfo is None:
            raise ValueError("naive timestamp")
        age = (datetime.now(timezone.utc) - captured).total_seconds()
        if age < -5:
            raise ValueError("future timestamp")
    except (TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(status_code=503, detail={"code": "PM_INVALID_TIMESTAMP"}) from exc
    coverage = _pick(payload.get("coverage"), COVERAGE_FIELDS)
    if any(coverage.get(name) != "ok" for name in ("account", "balance", "um_positions", "cm_positions")):
        raise HTTPException(status_code=503, detail={"code": "PM_INCOMPLETE_ACCOUNT"})
    account = _pick(payload.get("account"), ACCOUNT_FIELDS)
    if not account.get("account_equity_usd") or not account.get("account_status"):
        raise HTTPException(status_code=503, detail={"code": "PM_MISSING_ACCOUNT_VALUES"})
    if not isinstance(payload.get("balances"), list) or not isinstance(payload.get("positions"), list):
        raise HTTPException(status_code=503, detail={"code": "PM_MISSING_POSITIONS"})
    orders_ok = all(coverage.get(name) == "ok" for name in ("um_orders", "um_algo_orders", "cm_orders", "cm_conditional_orders", "margin_orders", "margin_oco_orders"))
    orders = payload.get("orders") if orders_ok else None
    if orders_ok and not isinstance(orders, list):
        raise HTTPException(status_code=503, detail={"code": "PM_MISSING_ORDERS"})
    order_time = payload.get("orders_captured_at")
    order_age = None
    if orders_ok:
        try:
            parsed_order_time = datetime.fromisoformat(str(order_time).replace("Z", "+00:00"))
            if parsed_order_time.tzinfo is None:
                raise ValueError("naive")
            order_age = (datetime.now(timezone.utc) - parsed_order_time).total_seconds()
        except (ValueError, TypeError, OverflowError):
            orders_ok = False
            orders = None
    return {
        "source": "binance_pm_classic", "captured_at": captured.isoformat(),
        "age_seconds": max(0, int(age)), "stale": age > 120,
        "account": account,
        "balances": [_pick(row, BALANCE_FIELDS) for row in payload["balances"] if isinstance(row, dict)],
        "positions": [_pick(row, POSITION_FIELDS) for row in payload["positions"] if isinstance(row, dict)],
        "orders": [_pick(row, ORDER_FIELDS) for row in orders] if orders_ok else None,
        "orders_age_seconds": max(0, int(order_age)) if order_age is not None else None,
        "orders_stale": not orders_ok or order_age is None or order_age > 120,
        "coverage": coverage,
    }


@router.get("/snapshot")
def private_pm_snapshot(response: Response, user: User = Depends(get_current_user)) -> dict:
    if not _allowed_user(user):
        raise HTTPException(status_code=403, detail={"code": "PM_ACCESS_DENIED"})
    url = _safe_url()
    token = os.getenv("RISKBOT_PM_SERVICE_TOKEN", "").strip()
    if len(token) < 32:
        raise HTTPException(status_code=503, detail={"code": "PM_BRIDGE_UNCONFIGURED"})
    try:
        with requests.Session() as client:
            client.trust_env = False
            upstream = client.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=3.5, allow_redirects=False)
        if upstream.status_code != 200 or len(upstream.content) > 2_000_000:
            raise HTTPException(status_code=503, detail={"code": "PM_UPSTREAM_UNAVAILABLE"})
        result = _snapshot(upstream.json())
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=503, detail={"code": "PM_UPSTREAM_UNAVAILABLE"}) from exc
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return result
