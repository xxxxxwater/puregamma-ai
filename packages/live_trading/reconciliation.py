"""Daily reconciliation: exchange balance vs PureGamma Ledger vs NAV Snapshot.

On any difference the service:
- pauses the user's LIVE mandates (new orders refused),
- keeps data sync running,
- records the differences (append-only),
- sends an ops alert,
- waits for manual resolution.

Historical ledger rows are NEVER modified or deleted.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from packages.database.models import (
    BrokerConnection,
    TradingMandate,
    TradingReconciliation,
)
from packages.live_trading import audit as audit_service
from packages.live_trading import ledger as ledger_service
from packages.live_trading import nav as nav_service
from packages.live_trading.enums import ReconciliationStatus
from packages.live_trading.gateway_adapter import ExecutionGateway, GatewayError


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _tolerance() -> Decimal:
    """MVP tolerance: 1 currency unit (USD). Configurable later."""
    return Decimal("1.00")


def reconcile_account(
    db: Session,
    *,
    user_id: str,
    account_id: str,
    mandate: TradingMandate | None = None,
    connection: BrokerConnection | None = None,
    gateway: ExecutionGateway,
    trace_id: str,
) -> TradingReconciliation:
    exchange_balance: dict = {}
    try:
        balances = gateway.account_balances(
            account_id, connection_id=connection.id if connection else None
        )
        exchange_balance = {
            "cash": str(balances.get("cash") or balances.get("available") or 0),
            "equity": str(balances.get("equity") or 0),
        }
        exchange_cash = _decimal(balances.get("cash") or balances.get("available"))
    except GatewayError as exc:
        # Gateway unreachable: record an error reconciliation and pause the
        # mandate — reconcile can never silently pass with no exchange data.
        row = TradingReconciliation(
            user_id=user_id,
            account_id=account_id,
            mandate_id=mandate.id if mandate else None,
            status=ReconciliationStatus.ERROR.value,
            exchange_balance_json={"error": str(exc)[:240]},
            ledger_balance_json={},
            nav_json={},
            differences_json=[{"source": "exchange_unavailable", "detail": str(exc)[:240]}],
            actions_json=["mandate_paused"],
            trace_id=trace_id,
        )
        db.add(row)
        if mandate:
            mandate.paused = True
            mandate.pause_reason = "reconciliation_exchange_unavailable"
        _notify_ops(
            user_id, account_id, "exchange unavailable during reconciliation; mandate paused"
        )
        db.flush()
        return row

    ledger_cash = ledger_service.cash_balance(db, account_id)
    ledger_balance = {"cash": str(ledger_cash)}

    snapshot = nav_service.latest_snapshot(db, user_id, account_id)
    nav_cash = _decimal(snapshot.cash) if snapshot else ledger_cash
    nav_balance = {"cash": str(nav_cash), "nav": str(snapshot.nav) if snapshot else None}

    differences: list[dict] = []
    tolerance = _tolerance()
    if abs(exchange_cash - ledger_cash) > tolerance:
        differences.append(
            {
                "source": "exchange_vs_ledger",
                "exchange": str(exchange_cash),
                "ledger": str(ledger_cash),
                "delta": str(exchange_cash - ledger_cash),
            }
        )
    if snapshot is not None and abs(exchange_cash - nav_cash) > tolerance:
        differences.append(
            {
                "source": "exchange_vs_nav",
                "exchange": str(exchange_cash),
                "nav_cash": str(nav_cash),
                "delta": str(exchange_cash - nav_cash),
            }
        )
    if snapshot is not None and snapshot.is_stale:
        differences.append({"source": "nav_stale", "detail": "latest NAV snapshot is stale"})

    status = (
        ReconciliationStatus.DISCREPANCY.value
        if differences
        else ReconciliationStatus.OK.value
    )
    actions: list[str] = []
    if differences and mandate:
        mandate.paused = True
        mandate.pause_reason = "reconciliation_discrepancy"
        actions.append("mandate_paused")
        actions.append("new_orders_forbidden")

    row = TradingReconciliation(
        user_id=user_id,
        account_id=account_id,
        mandate_id=mandate.id if mandate else None,
        status=status,
        exchange_balance_json=exchange_balance,
        ledger_balance_json=ledger_balance,
        nav_json=nav_balance,
        differences_json=differences,
        actions_json=actions,
        trace_id=trace_id,
    )
    db.add(row)
    audit_service.audit(
        db,
        user_id=user_id,
        action="LIVE_RECONCILIATION",
        status=status,
        trace_id=trace_id,
        idempotency_key=f"audit:reconcile:{trace_id}",
        actor_type="system",
        result_json={"account_id": account_id, "differences": differences, "actions": actions},
    )
    if differences:
        _notify_ops(
            user_id,
            account_id,
            f"LIVE reconciliation discrepancy ({len(differences)}); mandate paused. "
            f"Manual review required.",
        )
    db.flush()
    return row


def _notify_ops(user_id: str, account_id: str, message: str) -> None:
    try:
        from apps.api.services.ops_alert import notify_ops

        notify_ops(f"[live-trading] user={user_id} account={account_id} {message}")
    except Exception:
        pass
