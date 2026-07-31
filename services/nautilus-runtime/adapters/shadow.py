from __future__ import annotations

from app.exchange_gateway import MockExchangeGateway


class ShadowExecutionAdapter(MockExchangeGateway):
    """SHADOW mode gateway: real adapter market data, simulated fills.

    Wraps a real venue adapter for prices/order-book depth but never submits
    orders to it. Fills are simulated against the adapter's current order book
    (walk-the-book VWAP for the requested quantity) and accounted exactly like
    the paper gateway, so journal/positions/PnL/reconciliation all run against
    paper accounting with real market prices.
    """

    def __init__(self, real_adapter, store=None):
        super().__init__(store)
        self.real = real_adapter

    def health_check(self) -> dict:
        upstream = {}
        try:
            upstream = self.real.health_check()
        except Exception:
            upstream = {"status": "DEGRADED"}
        return {
            "status": "HEALTHY" if upstream.get("status") == "HEALTHY" else "DEGRADED",
            "adapter": f"shadow:{getattr(self.real, 'name', 'unknown')}",
            "live": False,
            "simulated_fills": True,
            "upstream": upstream,
        }

    def _book_fill(self, order: dict) -> tuple[float, float] | None:
        """VWAP for the full requested quantity, or None if book is too thin."""
        book = self.real.fetch_order_book(order["instrument"])
        levels = book["asks"] if str(order["side"]).upper() == "BUY" else book["bids"]
        remaining = float(order["quantity"])
        cost = 0.0
        for price, size in levels:
            take = min(remaining, float(size))
            cost += take * float(price)
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 0:
            return None
        return cost / float(order["quantity"]), float(order["quantity"])

    def submit_order(self, order: dict) -> dict:
        existing = self.orders.get(order["client_order_id"])
        if existing:
            return existing
        fill = self._book_fill(order)
        if fill is None:
            # No executable depth: rest the order without filling it.
            accepted = {
                **order,
                "exchange_order_id": None,
                "state": "ACCEPTED",
                "filled_quantity": 0.0,
                "remaining_quantity": float(order["quantity"]),
                "average_price": None,
                "shadow": True,
            }
            self.orders[order["client_order_id"]] = accepted
            return accepted
        vwap, _ = fill
        simulated = {
            **order,
            "fill_immediately": True,
            "mark_price": vwap,
            "shadow": True,
        }
        result = super().submit_order(simulated)
        result["shadow"] = True
        result["exchange_order_id"] = f"shadow-{result['exchange_order_id']}"
        self.orders[order["client_order_id"]] = result
        return result
