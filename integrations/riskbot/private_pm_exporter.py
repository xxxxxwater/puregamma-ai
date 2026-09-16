"""Private read-only bridge for the independent Binance PM riskbot.

Install as app/services/private_pm_exporter.py INSIDE the riskbot image; run
`asyncio.create_task(serve(snapshot, stop))` in riskbot's existing event loop.
Only joins the private riskbot/PureGamma network. NEVER publish its port.
There are no Binance API calls, trading actions or exposed raw API responses.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

log = logging.getLogger("riskbot.private_pm")
ORDER_COVERAGE = ("um_orders", "um_algo_orders", "cm_orders", "cm_conditional_orders", "margin_orders", "margin_oco_orders")
CORE_COVERAGE = ("account", "balance", "um_positions", "cm_positions")


def dec(value):
    return str(value) if value is not None else None


def utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def snapshot_data(service):
    snap = service.cache
    age = service.age_seconds(snap)
    if snap is None or age is None or age > 120:
        raise ValueError("account snapshot unavailable or stale")
    coverage = {name: getattr(snap.coverage, name) for name in (*CORE_COVERAGE, *ORDER_COVERAGE)}
    if any(coverage[name] != "ok" for name in CORE_COVERAGE):
        raise ValueError("incomplete PM account snapshot")
    a = snap.account
    if a.account_equity is None or a.account_status is None:
        raise ValueError("missing official PM equity or status")
    btc = snap.btc_usdt.price if snap.btc_usdt is not None else None
    btc_wallet = next((b.wallet_balance for b in snap.balances if b.asset.upper() == "BTC"), None)
    gross = sum((abs(p.notional_usd) for p in snap.positions if p.notional_usd is not None), Decimal(0))
    net = sum(((Decimal(-1) if p.side == "SHORT" else Decimal(1)) * abs(p.notional_usd)
               for p in snap.positions if p.notional_usd is not None), Decimal(0))
    def to_btc(value):
        return dec(value / btc) if value is not None and btc is not None and btc > 0 else None
    account = {
        "account_status": a.account_status,
        "uni_mmr": a.uni_mmr,
        "account_equity_usd": dec(a.account_equity),
        "actual_equity_usd": dec(a.actual_equity),
        "available_usd": dec(a.total_available_balance),
        "initial_margin_usd": dec(a.account_initial_margin),
        "maintenance_margin_usd": dec(a.account_maint_margin),
        "max_withdraw_usd": dec(a.virtual_max_withdraw_amount),
        "wallet_balance_usd": dec(a.total_wallet_balance),
        "unrealized_pnl_usd": dec(a.total_unrealized_pnl),
        "btc_usdt_mark": dec(btc),
        "btc_wallet_quantity": dec(btc_wallet),
        "equity_btc_equivalent": dec(a.equity_btc),
        "available_btc_equivalent": dec(a.available_btc),
        "gross_notional_usd": dec(gross),
        "net_notional_usd": dec(net),
        "gross_notional_btc_equivalent": to_btc(gross),
        "net_notional_btc_equivalent": to_btc(net),
        "gross_leverage_estimate": dec(gross / a.account_equity) if a.account_equity > 0 else None,
        "maintenance_to_equity_estimate": dec(a.derived.get("maintenance_margin_usage")),
    }
    balances = [{
        "asset": b.asset, "wallet_balance": dec(b.wallet_balance),
        "borrowed": dec(b.borrowed), "interest": dec(b.interest),
        "unrealized_pnl": dec(b.unrealized_pnl), "btc_equivalent": dec(b.btc_value),
        "usd_equivalent": dec(b.btc_value * btc) if b.btc_value is not None and btc is not None else None,
        "price_source": b.price.source if b.price is not None else None,
    } for b in snap.balances]
    order_age = time.monotonic() - service.last_full_orders_at if service.last_full_orders_at else None
    orders_ok = (order_age is not None and 0 <= order_age <= 120
                 and all(coverage[k] == "ok" for k in ORDER_COVERAGE))
    orders = snap.orders if orders_ok else []
    def protective(position):
        if not orders_ok:
            return "unknown"
        expected = "SELL" if position.side == "LONG" else "BUY"
        for order in orders:
            raw = order.raw or {}
            kind = str(raw.get("orderType") or raw.get("type") or order.order_type or "").upper()
            status = str(raw.get("algoStatus") or raw.get("status") or order.status or "").upper()
            side = str(raw.get("positionSide") or "BOTH").upper()
            # A full-close stop uses closePosition=true rather than reduceOnly.
            if (order.product == position.product and order.symbol == position.symbol
                and order.side == expected and ("STOP" in kind or "TRAILING_STOP" in kind)
                and status in {"NEW", "PARTIALLY_FILLED", "WORKING", "PENDING_NEW"}
                and (raw.get("closePosition") is True or raw.get("reduceOnly") is True)
                and side in {"BOTH", position.side}):
                return "present_unverified_quantity"
        return "missing"
    positions = [{
        "product": p.product, "symbol": p.symbol, "side": p.side,
        "position_side": str(p.raw.get("positionSide") or "BOTH"),
        "quantity": dec(p.position_amt), "quantity_unit": p.quantity_unit,
        "entry_price": dec(p.entry_price), "mark_price": dec(p.mark_price),
        "notional_usd": dec(p.notional_usd), "notional_btc_equivalent": dec(p.notional_btc),
        "unrealized_pnl": dec(p.unrealized_pnl), "liquidation_price": dec(p.liquidation_price),
        "leverage": p.leverage, "update_time_ms": int(p.update_time) if p.update_time else None,
        "protection_status": protective(p),
    } for p in snap.positions]
    order_rows = [{
        "product": o.product, "kind": o.kind, "symbol": o.symbol,
        "order_id": o.order_id, "client_order_id": o.raw.get("clientAlgoId") or o.raw.get("clientOrderId"),
        "side": o.side, "position_side": o.raw.get("positionSide"),
        "order_type": o.raw.get("orderType") or o.raw.get("type") or o.order_type,
        "status": o.raw.get("algoStatus") or o.status,
        "quantity": dec(o.quantity), "executed_quantity": dec(o.raw.get("executedQty")),
        "price": dec(o.price), "trigger_price": dec(o.raw.get("triggerPrice") or o.stop_price),
        "reduce_only": bool(o.reduce_only), "close_position": bool(o.raw.get("closePosition")),
        "created_time_ms": o.raw.get("createTime") or o.create_time,
        "updated_time_ms": o.raw.get("updateTime"),
    } for o in orders]
    return {
        "source": "binance_pm_classic", "captured_at": snap.captured_at.isoformat(),
        "orders_captured_at": utc(time.time() - order_age) if orders_ok else None,
        "account": account, "coverage": coverage, "balances": balances,
        "positions": positions, "orders": order_rows if orders_ok else None,
    }


def _open_history(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS pm_nav_history (captured_at TEXT PRIMARY KEY, equity_usd TEXT NOT NULL, equity_btc TEXT, btc_price TEXT, source TEXT NOT NULL)")
    db.commit()
    return db


async def serve(snapshot, stop: asyncio.Event):
    """Read existing riskbot cache; never trigger a Binance REST call."""
    token = os.getenv("RISKBOT_PM_SERVICE_TOKEN", "")
    if len(token) < 32:
        log.info("private PM exporter disabled: no service token")
        return
    host = os.getenv("RISKBOT_PM_BIND_HOST", "127.0.0.1")
    port = int(os.getenv("RISKBOT_PM_BIND_PORT", "8769"))
    db_path = os.getenv("RISKBOT_PM_HISTORY_DB", "/data/private_pm_history.sqlite3")
    db = _open_history(db_path)

    async def handle(reader, writer):
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
            if len(request) > 8192:
                return
            lines = request.decode("ascii", "replace").split("\r\n")
            parts = lines[0].split(" ")
            if len(parts) != 3 or parts[0] != "GET":
                code, body = 405, {"code": "METHOD_NOT_ALLOWED"}
            else:
                headers = dict((k.strip().lower(), v.strip()) for line in lines[1:] if ":" in line for k, v in [line.split(":", 1)])
                authorization = headers.get("authorization", "")
                if not hmac.compare_digest(authorization, "Bearer " + token):
                    code, body = 403, {"code": "DENIED"}
                else:
                    url = urlsplit(parts[1]); params = parse_qs(url.query)
                    if url.path == "/v1/portfolio/snapshot" and not url.query:
                        try:
                            body = snapshot_data(snapshot); code = 200
                        except ValueError:
                            code, body = 503, {"code": "STALE_OR_INCOMPLETE"}
                    elif url.path == "/v1/portfolio/history" and params.get("days", [None]) == ["90"]:
                        cutoff = utc(time.time() - 90 * 86400)
                        rows = db.execute("SELECT captured_at,equity_usd,equity_btc,btc_price FROM pm_nav_history WHERE captured_at >= ? ORDER BY captured_at LIMIT 150000", (cutoff,)).fetchall()
                        code, body = 200, {"source": "binance_pm_classic", "points": [dict(zip(("captured_at", "equity_usd", "equity_btc", "btc_price"), row)) for row in rows]}
                    else:
                        code, body = 404, {"code": "NOT_FOUND"}
            encoded = json.dumps(body, separators=(",", ":")).encode()
            writer.write((f"HTTP/1.1 {code} {'OK' if code == 200 else 'Error'}\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: {len(encoded)}\r\n\r\n").encode() + encoded)
            await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, ValueError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    server = await asyncio.start_server(handle, host, port, limit=8192)
    log.info("private PM exporter listening on internal interface")
    try:
        async with server:
            last = None
            while not stop.is_set():
                try:
                    data = snapshot_data(snapshot)
                    if data["captured_at"] != last:
                        account = data["account"]
                        if account["account_equity_usd"] is not None:
                            db.execute("INSERT OR IGNORE INTO pm_nav_history VALUES (?,?,?,?,?)", (data["captured_at"], account["account_equity_usd"], account["equity_btc_equivalent"], account["btc_usdt_mark"], data["source"]))
                            db.execute("DELETE FROM pm_nav_history WHERE captured_at < ?", (utc(time.time() - 90 * 86400),))
                            db.commit(); last = data["captured_at"]
                except (ValueError, sqlite3.Error) as exc:
                    log.debug("private PM snapshot history skipped: %s", type(exc).__name__)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass
    finally:
        db.close()
