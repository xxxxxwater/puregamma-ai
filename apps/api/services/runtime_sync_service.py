from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from apps.api.services import custody_service
from packages.database.models import (
    AccountSnapshot,
    OrderIntent,
    OrderJournal,
    PositionSnapshot,
    SignalEvent,
    StrategyRun,
    TradingAccount,
    TradingAuditLog,
    utcnow,
)
from packages.trading.runtime_client import NautilusRuntimeClient


def _parse_time(value: str | None) -> datetime:
    if not value:
        return utcnow()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _source_url(provider: str, asset: str) -> str:
    if provider == "hyperliquid_public":
        return "https://api.hyperliquid.xyz/info"
    return f"https://api.exchange.coinbase.com/products/{asset}-USD/ticker"


def _state_fingerprint(state: dict) -> str:
    value = {
        "account": state.get("account", {}),
        "positions": state.get("positions", []),
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:24]


def sync_runtime_account(
    db: Session,
    account: TradingAccount,
    *,
    runtime: NautilusRuntimeClient | None = None,
) -> dict:
    client = runtime or NautilusRuntimeClient()
    state = client.account_state(account.id)
    events = client.events(limit=500).get("events", [])
    runs = {
        row.runtime_run_id: row
        for row in db.query(StrategyRun).filter_by(user_id=account.user_id).all()
    }
    counts = {"snapshots": 0, "orders": 0, "signals": 0}

    fingerprint = _state_fingerprint(state)
    snapshot_key = f"runtime-state:{account.id}:{fingerprint}"
    if not db.query(TradingAuditLog).filter_by(idempotency_key=snapshot_key).first():
        account_value = state.get("account", {})
        db.add(
            AccountSnapshot(
                user_id=account.user_id,
                account_id=account.id,
                balance=float(account_value.get("balance", 0)),
                equity=float(account_value.get("equity", 0)),
                available_margin=float(account_value.get("available_margin", 0)),
                daily_pnl=float(account_value.get("daily_pnl", 0)),
                drawdown=float(account_value.get("drawdown", 0)),
                exposure=float(account_value.get("exposure", 0)),
                stale=bool(account_value.get("stale", False)),
                raw_event_reference={
                    "source": "nautilus-runtime",
                    "fingerprint": fingerprint,
                },
            )
        )
        for value in state.get("positions", []):
            run = runs.get(value.get("run_id"))
            db.add(
                PositionSnapshot(
                    user_id=account.user_id,
                    account_id=account.id,
                    strategy_id=run.strategy_id if run else None,
                    run_id=run.id if run else None,
                    instrument=value["instrument"],
                    quantity=float(value["quantity"]),
                    side=value["side"],
                    average_price=float(value["average_price"]),
                    mark_price=float(value["mark_price"]),
                    unrealized_pnl=float(value.get("unrealized_pnl", 0)),
                    realized_pnl=float(value.get("realized_pnl", 0)),
                    leverage=float(value.get("leverage", 1)),
                    raw_event_reference={
                        "source": "nautilus-runtime",
                        "fingerprint": fingerprint,
                    },
                    captured_at=_parse_time(value.get("updated_at")),
                )
            )
        db.add(
            TradingAuditLog(
                user_id=account.user_id,
                action="SYNC_RUNTIME_STATE",
                status="COMPLETED",
                actor_type="scheduler",
                request_json={"account_id": account.id},
                result_json={"positions": len(state.get("positions", []))},
                idempotency_key=snapshot_key,
            )
        )
        counts["snapshots"] = 1

    for value in state.get("orders", []):
        client_order_id = value["client_order_id"]
        sequence = int(value.get("sequence", 1))
        order_key = f"runtime-order:{client_order_id}:{sequence}"
        if db.query(OrderJournal).filter_by(idempotency_key=order_key).first():
            continue
        run = runs.get(value.get("run_id"))
        intent_key = f"runtime-auto:{client_order_id}"
        intent = (
            db.query(OrderIntent).filter_by(idempotency_key=intent_key).one_or_none()
        )
        if not intent:
            intent = OrderIntent(
                user_id=account.user_id,
                strategy_id=run.strategy_id if run else None,
                strategy_version=run.strategy_version if run else None,
                run_id=run.id if run else None,
                account_id=account.id,
                instrument=value["instrument"],
                venue=value.get("venue", "MOCK"),
                direction=value.get("side", value.get("direction", "BUY")),
                quantity=float(value["quantity"]),
                notional=float(value.get("notional", 0)),
                leverage=float(value.get("leverage", 1)),
                order_type=value.get("order_type", "MARKET"),
                reduce_only=bool(value.get("reduce_only", False)),
                execution_mode="PAPER",
                status="EXECUTED",
                risk_limits_json=value.get("risk_policy", {}),
                idempotency_key=intent_key,
                approval_status="STRATEGY_APPROVED",
                expires_at=utcnow(),
                raw_event_reference={"source": "nautilus-runtime"},
            )
            db.add(intent)
            db.flush()
        # Custody-linked accounts: order intent creation freezes the quote
        # notional (BUY) and the fill settles debit/credit into custody.
        # Unlinked accounts are a no-op. An insufficient hold never wedges the
        # sync loop — the journal row is annotated instead of faking balances.
        side = value.get("side", value.get("direction", "BUY"))
        custody_error = None
        try:
            custody_service.apply_order_freeze(
                db,
                trading_account=account,
                user_id=account.user_id,
                order_ref=client_order_id,
                side=side,
                notional=value.get("notional", 0),
                quote_asset=account.base_currency,
            )
            custody_service.apply_fill_settlement(
                db,
                trading_account=account,
                user_id=account.user_id,
                fill_ref=f"{client_order_id}:{sequence}",
                side=side,
                state=value["state"],
                quantity=float(value["quantity"]),
                filled_quantity=float(value.get("filled_quantity", 0)),
                average_price=value.get("average_price"),
                notional=value.get("notional", 0),
                quote_asset=account.base_currency,
            )
        except custody_service.InsufficientCustodyBalance:
            custody_error = "CUSTODY_INSUFFICIENT_BALANCE"
        db.add(
            OrderJournal(
                user_id=account.user_id,
                account_id=account.id,
                strategy_id=run.strategy_id if run else None,
                run_id=run.id if run else None,
                order_intent_id=intent.id,
                client_order_id=client_order_id,
                exchange_order_id=value.get("exchange_order_id"),
                sequence=sequence,
                state=value["state"],
                instrument=value["instrument"],
                side=side,
                quantity=float(value["quantity"]),
                filled_quantity=float(value.get("filled_quantity", 0)),
                remaining_quantity=float(value.get("remaining_quantity", 0)),
                average_price=value.get("average_price"),
                reduce_only=bool(value.get("reduce_only", False)),
                event_json=value,
                raw_event_reference={"source": "nautilus-runtime"},
                idempotency_key=order_key,
                error_code=custody_error or value.get("error"),
            )
        )
        counts["orders"] += 1

    for event in events:
        if event.get("event_type") != "STRATEGY_SIGNAL":
            continue
        value = event.get("payload", {})
        run = runs.get(value.get("run_id"))
        if not run or run.account_id != account.id:
            continue
        signal_key = f"runtime-signal:{event['id']}"
        if db.query(SignalEvent).filter_by(idempotency_key=signal_key).first():
            continue
        provider = value.get("provider", "unknown")
        asset = value.get("asset", "UNKNOWN")
        change = float(value.get("change", 0))
        db.add(
            SignalEvent(
                user_id=account.user_id,
                strategy_id=run.strategy_id,
                strategy_version=run.strategy_version,
                run_id=run.id,
                source_ids=[f"{provider}:{event['id']}"],
                source_urls=[_source_url(provider, asset)],
                data_timestamp=_parse_time(value.get("source_timestamp")),
                fetch_timestamp=_parse_time(event.get("created_at")),
                freshness=1.0,
                credibility_score=0.8,
                sentiment_score=max(-1.0, min(1.0, change * 100)),
                confidence=min(1.0, 0.5 + abs(change) * 10),
                asset=asset,
                model_version="runtime-market-v1",
                feature_version="public-price-change-v1",
                signal_direction=value.get("direction", "HOLD"),
                signal_strength=min(
                    1.0, abs(change) / max(float(value.get("threshold", 0.002)), 0.0001)
                ),
                target_position=1.0 if value.get("direction") == "LONG" else -1.0,
                execution_note="Generated by an approved PAPER/SHADOW strategy runtime.",
                risk_state="PAPER_ONLY",
                raw_event_reference={
                    "runtime_event_id": event["id"],
                    "provider": provider,
                },
                idempotency_key=signal_key,
            )
        )
        counts["signals"] += 1

    db.commit()
    return {"account_id": account.id, **counts}
