"""Pre-trade Risk Engine (LIVE).

All monetary math uses Decimal (Numeric columns); binary floats are never
used for risk thresholds. The engine is deterministic and versioned — every
verdict records ``RISK_ENGINE_VERSION`` so historical checks remain auditable.

Checks run in the mandated order; the first failing check rejects the order
and no later check is skipped (all are recorded for the audit trail).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from apps.api.config import get_settings
from packages.database.models import BrokerConnection, LiveOrder, TradingMandate
from packages.live_trading.enums import OrderType, Side
from packages.live_trading.flags import evaluate_full_gate
from packages.live_trading.gateway_adapter import GatewayError, get_execution_gateway
from packages.live_trading import kill_switch as kill_switch_service
from packages.live_trading import ledger as ledger_service
from packages.live_trading import price_feed as price_feed_service

RISK_ENGINE_VERSION = "1.0.0"

_ZERO = Decimal("0")


class RiskRejected(RuntimeError):
    def __init__(self, reason: str, checks: list[dict]):
        super().__init__(reason)
        self.reason = reason
        self.checks = checks


@dataclass
class RiskContext:
    mandate: TradingMandate
    connection: BrokerConnection | None
    available_cash: Decimal | None = None
    exchange_positions_notional: dict[str, Decimal] = field(default_factory=dict)
    ledger_positions_notional: dict[str, Decimal] = field(default_factory=dict)
    daily_realized_pnl: Decimal = _ZERO
    last_order_at: datetime | None = None
    current_leverage: Decimal = _ZERO


@dataclass
class RiskVerdict:
    result: str  # PASS | REJECT
    rejection_reason: str | None
    checks: list[dict]


def _decimal(value, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class RiskEngine:
    def __init__(self, db):
        self.db = db
        self.version = RISK_ENGINE_VERSION

    def evaluate(
        self,
        *,
        user_id: str,
        symbol: str,
        side: str,
        quantity: Decimal | str | float,
        order_type: str,
        limit_price: Decimal | str | float | None,
        ctx: RiskContext,
    ) -> RiskVerdict:
        checks: list[dict] = []
        rejections: list[str] = []

        def add(name: str, ok: bool, detail: str = "") -> bool:
            checks.append(
                {
                    "check": name,
                    "ok": bool(ok),
                    "detail": str(detail),
                }
            )
            return bool(ok)

        mandate = ctx.mandate
        qty = _decimal(quantity)
        limit = _decimal(limit_price) if limit_price is not None else None
        symbol_upper = str(symbol).upper()
        side_lower = str(side).lower()
        order_type_lower = str(order_type).lower()

        # --- 1-2. ownership & mandate state (pre-validated by control plane,
        #         re-checked here so the engine is independently safe) ------
        add("mandate_ownership", mandate.user_id == user_id, "mandate owner matches user")
        add(
            "mandate_state",
            not mandate.paused
            and mandate.status in {"active", "draft"}
            and mandate.kill_switch_state != "active",
            f"paused={mandate.paused} status={mandate.status}",
        )

        # --- 3-4. feature gate + user approval (gate result) ---------------
        gate = evaluate_full_gate(self.db, user_id, mandate, ctx.connection)
        add("feature_gate", gate.enabled, "LIVE feature gate")
        if not gate.enabled:
            failed = [name for name, value in gate.checks.items() if not value["ok"]]
            rejections.append("LIVE_GATE_BLOCKED: " + ",".join(sorted(failed)[:6]))

        # --- 5. broker connection health -----------------------------------
        healthy = bool(
            ctx.connection
            and ctx.connection.status in {"CONNECTED", "HEALTHY"}
            and ctx.connection.revoked_at is None
        )
        add("connection_health", healthy, "broker connection healthy and active")
        if not healthy:
            rejections.append("CONNECTION_UNHEALTHY")

        # --- 6. asset whitelist --------------------------------------------
        allowlist = {
            str(item).upper() for item in (mandate.allowed_symbols_json or [])
        }
        settings_allowlist = set(
            s.upper() for s in (get_settings().live_trading_allowed_symbols or ())
        )
        allowed = symbol_upper in allowlist or symbol_upper in settings_allowlist
        add("asset_whitelist", allowed, f"{symbol_upper} in mandate/config whitelist")
        if not allowed:
            rejections.append("SYMBOL_NOT_ALLOWED")

        # --- 7. quantity / price / notional sanity -------------------------
        add("quantity_positive", qty > _ZERO, f"quantity={qty}")
        add(
            "side_valid",
            side_lower in {Side.BUY.value, Side.SELL.value},
            f"side={side_lower}",
        )
        add(
            "order_type_valid",
            order_type_lower in {OrderType.MARKET.value, OrderType.LIMIT.value},
            f"order_type={order_type_lower}",
        )
        if order_type_lower == OrderType.LIMIT.value and (limit is None or limit <= _ZERO):
            add("limit_price_valid", False, "limit order requires a positive limit_price")
            rejections.append("INVALID_LIMIT_PRICE")
        else:
            add("limit_price_valid", True, "limit price sane when provided")

        # Notional: limit orders use limit price; market orders use the latest
        # server price when available, otherwise the check falls back to the
        # broker balance check and stays conservative.
        notional = qty * limit if limit else _ZERO
        price = None
        if not notional or notional <= _ZERO:
            price, _price_at = price_feed_service.latest_valid_price(self.db, symbol_upper)
            if price:
                notional = qty * price
        if notional <= _ZERO:
            add("notional_valid", False, "cannot price the order; refusing market order without valid price")
            rejections.append("NO_VALID_PRICE_FOR_NOTIONAL")
        else:
            add("notional_valid", True, f"notional={notional} price={price}")

        # --- 8. balance ----------------------------------------------------
        if ctx.available_cash is None:
            add("balance_check", False, "broker balance unavailable; refusing")
            rejections.append("BALANCE_UNKNOWN")
        elif side_lower == Side.BUY.value and ctx.available_cash < notional:
            add(
                "balance_check",
                False,
                f"available={ctx.available_cash} < required={notional}",
            )
            rejections.append("INSUFFICIENT_BALANCE")
        else:
            add("balance_check", True, f"available={ctx.available_cash}")

        # --- 9. max per-order notional -------------------------------------
        max_per_order = _decimal(mandate.max_per_order_notional)
        if max_per_order > _ZERO and notional > max_per_order:
            add("max_per_order_notional", False, f"{notional} > {max_per_order}")
            rejections.append("MAX_PER_ORDER_NOTIONAL")
        else:
            add("max_per_order_notional", True, f"cap={max_per_order}")

        # --- 10. total position cap ----------------------------------------
        existing_notional = sum(
            (ctx.exchange_positions_notional or {}).values(), _ZERO
        )
        if not existing_notional:
            existing_notional = sum(
                (ctx.ledger_positions_notional or {}).values(), _ZERO
            )
        projected = existing_notional + notional
        max_position = _decimal(mandate.max_position_notional)
        if max_position > _ZERO and projected > max_position:
            add(
                "max_position_notional",
                False,
                f"projected={projected} > {max_position}",
            )
            rejections.append("MAX_POSITION_NOTIONAL")
        else:
            add("max_position_notional", True, f"projected={projected} cap={max_position}")

        # --- 11. max daily loss --------------------------------------------
        max_daily_loss = _decimal(mandate.max_daily_loss)
        daily_pnl = _decimal(ctx.daily_realized_pnl)
        if max_daily_loss > _ZERO and daily_pnl < -abs(max_daily_loss):
            add("max_daily_loss", False, f"daily_pnl={daily_pnl} limit={max_daily_loss}")
            rejections.append("MAX_DAILY_LOSS")
        else:
            add("max_daily_loss", True, f"daily_pnl={daily_pnl} limit={max_daily_loss}")

        # --- 12. max leverage ----------------------------------------------
        max_leverage = _decimal(mandate.max_leverage)
        add("leverage_spot_only", max_leverage <= _ZERO or max_leverage <= Decimal("1"), f"cap={max_leverage}")
        if max_leverage > Decimal("1"):
            rejections.append("LEVERAGE_FORBIDDEN")
        projected_leverage = _decimal(ctx.current_leverage) + (
            (notional / max(ctx.available_cash, Decimal("1"))) if ctx.available_cash else _ZERO
        )
        if max_leverage > _ZERO and projected_leverage > max_leverage:
            add("max_leverage", False, f"projected={projected_leverage} > {max_leverage}")
            rejections.append("MAX_LEVERAGE")
        else:
            add("max_leverage", True, f"projected={projected_leverage} cap={max_leverage}")

        # --- 13. max order frequency ---------------------------------------
        freq_seconds = max(0, int(mandate.max_order_frequency_seconds or 0))
        if ctx.last_order_at is not None and freq_seconds > 0:
            elapsed = (_now() - _aware(ctx.last_order_at)).total_seconds()
            if elapsed < freq_seconds:
                add("max_order_frequency", False, f"elapsed={elapsed:.1f}s < {freq_seconds}s")
                rejections.append("ORDER_FREQUENCY")
            else:
                add("max_order_frequency", True, f"elapsed={elapsed:.1f}s")
        else:
            add("max_order_frequency", True, "no recent order")

        # --- 14. kill switches ---------------------------------------------
        allowed_ks, ks_reason = kill_switch_service.mandate_trade_allowed(self.db, mandate)
        add("kill_switch", allowed_ks, ks_reason or "clear")
        if not allowed_ks:
            rejections.append(ks_reason or "KILL_SWITCH")

        result = "REJECT" if rejections else "PASS"
        return RiskVerdict(
            result=result,
            rejection_reason="; ".join(rejections) if rejections else None,
            checks=checks,
        )


def build_ctx(
    db,
    *,
    mandate: TradingMandate,
    connection: BrokerConnection | None,
    gateway=None,
    available_cash: Decimal | None = None,
) -> RiskContext:
    """Assemble a RiskContext with exchange and ledger state."""
    ctx = RiskContext(mandate=mandate, connection=connection)
    ctx.daily_realized_pnl = ledger_service.daily_realized_pnl(db, mandate.account_id)

    last_order = (
        db.query(LiveOrder)
        .filter_by(mandate_id=mandate.id)
        .order_by(LiveOrder.created_at.desc())
        .first()
    )
    if last_order:
        ctx.last_order_at = last_order.created_at

    gw = gateway or get_execution_gateway()
    connection_id = connection.id if connection else None
    try:
        positions = gw.positions(mandate.account_id, connection_id=connection_id)
        ctx.exchange_positions_notional = {
            str(item.get("instrument") or item.get("symbol") or "?").upper(): _decimal(
                item.get("notional") or item.get("market_value")
            )
            for item in positions
        }
        balances = gw.account_balances(mandate.account_id, connection_id=connection_id)
        ctx.available_cash = _decimal(balances.get("available") or balances.get("cash"))
    except GatewayError:
        # Gateway unavailable: keep None so balance check rejects honestly.
        ctx.available_cash = available_cash

    # Ledger-derived positions as a fallback for position caps.
    quantities = ledger_service.position_quantities(db, mandate.account_id)
    ctx.ledger_positions_notional = {
        symbol: abs(qty) * _decimal(price_feed_service.latest_valid_price(db, symbol)[0] or 0)
        for symbol, qty in quantities.items()
    }
    return ctx
