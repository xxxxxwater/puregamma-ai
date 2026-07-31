from __future__ import annotations

TERMINAL_STATES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}


class RuntimeReconciler:
    def __init__(self, store, exchange, risk):
        self.store = store
        self.exchange = exchange
        self.risk = risk

    def reconcile(self, account_id: str) -> dict:
        # Compare only the LATEST journal row per order: append-only history
        # rows of terminal orders are not open orders.
        local = [
            order
            for order in self.store.latest_orders(account_id)
            if order["state"] not in TERMINAL_STATES
        ]
        remote = self.exchange.reconcile(account_id)
        remote_ids = {item["client_order_id"] for item in remote["open_orders"]}
        unknown = [
            item["client_order_id"]
            for item in local
            if item["client_order_id"] not in remote_ids
            and item["state"] not in {"CREATED", "PREPARED"}
        ]
        local_fills = sum(
            1
            for order in self.store.latest_orders(account_id)
            if order["state"] == "FILLED"
        )
        remote_fills = remote.get("fills", [])
        drift = {
            "unknown_open_orders": unknown,
            "local_fills": local_fills,
            "adapter_fills": len(remote_fills),
            "fills_diverged": local_fills != len(remote_fills),
        }
        if unknown:
            self.risk.pause_opening_accounts.add(account_id)
        else:
            self.risk.pause_opening_accounts.discard(account_id)
        return {
            "status": "RECONCILIATION_REQUIRED" if unknown else "RECONCILED",
            "account_id": account_id,
            "unknown_orders": unknown,
            "local_open_orders": local,
            "exchange": remote,
            "drift": drift,
            "opening_paused": bool(unknown),
        }
