from __future__ import annotations

TERMINAL_STATES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}


def _fill_notional(fill: dict) -> float:
    """Notional of one fill row, tolerating quantity/price or amount fields."""
    quantity = float(fill.get("quantity") or fill.get("filled_quantity") or 0)
    price = float(fill.get("price") or fill.get("average_price") or 0)
    if quantity and price:
        return quantity * price
    return float(fill.get("amount") or fill.get("notional") or 0)


def _fill_quantity(fill: dict) -> float:
    """Filled quantity of one fill row, tolerating quantity variants."""
    return float(fill.get("quantity") or fill.get("filled_quantity") or 0)


class RuntimeReconciler:
    def __init__(self, store, exchange, risk):
        self.store = store
        self.exchange = exchange
        self.risk = risk

    def reconcile(self, account_id: str) -> dict:
        journal = self.store.latest_orders(account_id)
        # Compare only the LATEST journal row per order: append-only history
        # rows of terminal orders are not open orders.
        local = [
            order for order in journal if order["state"] not in TERMINAL_STATES
        ]
        remote = self.exchange.reconcile(account_id)
        remote_orders = remote.get("open_orders", [])
        remote_ids = {item["client_order_id"] for item in remote_orders}
        local_ids = {item["client_order_id"] for item in journal}

        # Blind spot 1 (fixed): orders that exist remotely but never appear in
        # the local journal at all — someone/something placed them without this
        # runtime knowing. Previously only local->remote drift was detected.
        remote_only = [
            item["client_order_id"]
            for item in remote_orders
            if item["client_order_id"] not in local_ids
        ]

        unknown = [
            item["client_order_id"]
            for item in local
            if item["client_order_id"] not in remote_ids
            and item["state"] not in {"CREATED", "PREPARED"}
        ]

        # Blind spot 2 (fixed): fills compared on notional (quantity x price)
        # in addition to count, so equal-count but diverging-value fills are
        # flagged instead of silently reconciling.
        local_fills = [
            order
            for order in journal
            if order["state"] == "FILLED"
        ]
        local_fill_count = len(local_fills)
        local_fill_notional = sum(
            float(order.get("filled_quantity") or 0)
            * float(order.get("average_price", order.get("mark_price", 0)) or 0)
            for order in local_fills
        )
        local_fill_quantity = sum(
            float(order.get("filled_quantity") or 0) for order in local_fills
        )
        remote_fills = remote.get("fills", [])
        remote_fill_count = len(remote_fills)
        remote_fill_notional = sum(_fill_notional(fill) for fill in remote_fills)
        remote_fill_quantity = sum(_fill_quantity(fill) for fill in remote_fills)
        fills_diverged = (
            local_fill_count != remote_fill_count
            or abs(local_fill_notional - remote_fill_notional) > 1e-6
        )
        quantity_diverged = (
            abs(local_fill_quantity - remote_fill_quantity) > 1e-6
        )

        drift = {
            "unknown_open_orders": unknown,
            "remote_only_orders": remote_only,
            "local_fills": local_fill_count,
            "adapter_fills": remote_fill_count,
            "local_fill_notional": round(local_fill_notional, 8),
            "adapter_fill_notional": round(remote_fill_notional, 8),
            "local_fill_quantity": round(local_fill_quantity, 8),
            "adapter_fill_quantity": round(remote_fill_quantity, 8),
            "fills_diverged": fills_diverged,
            "fill_amount_diverged": fills_diverged,
            "fill_quantity_diverged": quantity_diverged,
        }

        needs_pause = bool(unknown or remote_only or fills_diverged)
        if needs_pause:
            self.risk.pause_opening(account_id)
        else:
            self.risk.resume_opening(account_id)
        return {
            "status": "RECONCILIATION_REQUIRED" if needs_pause else "RECONCILED",
            "account_id": account_id,
            "unknown_orders": unknown,
            "remote_only_orders": remote_only,
            "local_open_orders": local,
            "exchange": remote,
            "drift": drift,
            "opening_paused": needs_pause,
        }
