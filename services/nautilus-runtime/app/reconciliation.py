from __future__ import annotations


class RuntimeReconciler:
    def __init__(self, store, exchange, risk):
        self.store = store
        self.exchange = exchange
        self.risk = risk

    def reconcile(self, account_id: str) -> dict:
        local = self.store.open_orders(account_id)
        remote = self.exchange.reconcile(account_id)
        remote_ids = {item["client_order_id"] for item in remote["open_orders"]}
        unknown = [
            item["client_order_id"]
            for item in local
            if item["client_order_id"] not in remote_ids
            and item["state"] not in {"CREATED", "PREPARED"}
        ]
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
            "opening_paused": bool(unknown),
        }
