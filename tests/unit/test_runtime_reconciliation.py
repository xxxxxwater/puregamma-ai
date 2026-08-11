from __future__ import annotations

import sys
from pathlib import Path

RUNTIME_ROOT = Path(__file__).parents[2] / "services" / "nautilus-runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from app.reconciliation import RuntimeReconciler  # noqa: E402
from app.risk_gateway import RuntimeRiskGateway  # noqa: E402


def _order(cid: str, state: str, *, quantity: float = 1.0, filled_quantity: float = 0.0, average_price: float | None = None) -> dict:
    order = {
        "client_order_id": cid,
        "state": state,
        "quantity": quantity,
        "filled_quantity": filled_quantity,
        "account_id": "acct-1",
    }
    if average_price is not None:
        order["average_price"] = average_price
    return order


class FakeStore:
    def __init__(self, orders: list[dict]):
        self._orders = orders

    def latest_orders(self, account_id: str | None = None) -> list[dict]:
        return list(self._orders)


class FakeExchange:
    def __init__(self, open_orders: list[dict], fills: list[dict]):
        self._open = open_orders
        self._fills = fills

    def reconcile(self, account_id: str) -> dict:
        return {"open_orders": self._open, "fills": self._fills}


def _reconciler(orders, open_orders, fills, risk=None):
    store = FakeStore(orders)
    exchange = FakeExchange(open_orders, fills)
    risk = risk or RuntimeRiskGateway()
    return RuntimeReconciler(store, exchange, risk), risk


def test_reconciled_when_local_open_matches_remote():
    local = [_order("a1", "SUBMITTED")]
    result, risk = _reconciler(local, [_order("a1", "SUBMITTED")], [])
    assert result["status"] == "RECONCILED"
    assert result["opening_paused"] is False
    assert "acct-1" not in risk.pause_opening_accounts


def test_unknown_local_open_order_pauses_opening():
    # Local open order the exchange knows nothing about (state != CREATED/PREPARED).
    local = [_order("a1", "SUBMITTED")]
    result, risk = _reconciler(local, [], [])
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["drift"]["unknown_open_orders"] == ["a1"]
    assert "acct-1" in risk.pause_opening_accounts


def test_created_or_prepared_local_not_flagged_unknown():
    local = [_order("a1", "PREPARED")]
    result, _ = _reconciler(local, [], [])
    assert result["drift"]["unknown_open_orders"] == []


def test_remote_only_order_pauses_opening():
    # Order the exchange holds that this runtime has no journal row for at all.
    local = []
    remote = [_order("rogue-1", "ACCEPTED")]
    result, risk = _reconciler(local, remote, [])
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["drift"]["remote_only_orders"] == ["rogue-1"]
    assert "acct-1" in risk.pause_opening_accounts


def test_fill_notional_divergence_pauses_opening():
    # Equal fill COUNT but different notional (quantity x price) must be flagged.
    local = [_order("f1", "FILLED", quantity=1.0, filled_quantity=1.0, average_price=100.0)]
    remote_fills = [_order("f1", "FILLED", quantity=1.0, filled_quantity=1.0, average_price=101.0)]
    result, risk = _reconciler(local, [], remote_fills)
    assert result["drift"]["fills_diverged"] is True
    assert result["drift"]["fill_amount_diverged"] is True
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert "acct-1" in risk.pause_opening_accounts


def test_fill_quantity_divergence_paused():
    local = [_order("f1", "FILLED", quantity=1.0, filled_quantity=0.5, average_price=100.0)]
    remote_fills = [_order("f1", "FILLED", quantity=1.0, filled_quantity=1.0, average_price=100.0)]
    result, _ = _reconciler(local, [], remote_fills)
    assert result["drift"]["fill_quantity_diverged"] is True
    assert result["drift"]["fills_diverged"] is True


def test_pause_cleared_when_reconciled_again():
    local = [_order("a1", "SUBMITTED")]
    risk = RuntimeRiskGateway()
    risk.pause_opening("acct-1")
    result, _ = _reconciler(local, [_order("a1", "SUBMITTED")], [], risk=risk)
    assert result["status"] == "RECONCILED"
    assert "acct-1" not in risk.pause_opening_accounts
