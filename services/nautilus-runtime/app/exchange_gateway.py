from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class ExchangeGateway(ABC):
    @abstractmethod
    def health_check(self) -> dict: ...
    @abstractmethod
    def fetch_account(self, account_id: str) -> dict: ...
    @abstractmethod
    def fetch_positions(self, account_id: str) -> list[dict]: ...
    @abstractmethod
    def fetch_open_orders(self, account_id: str) -> list[dict]: ...
    @abstractmethod
    def submit_order(self, order: dict) -> dict: ...
    @abstractmethod
    def cancel_order(self, account_id: str, client_order_id: str) -> dict: ...
    @abstractmethod
    def reconcile(self, account_id: str) -> dict: ...


class MockExchangeGateway(ExchangeGateway):
    def __init__(self, store=None):
        self.store = store
        self.orders: dict[str, dict] = {
            order["client_order_id"]: order
            for order in (store.latest_orders() if store else [])
        }
        self.positions: dict[tuple[str, str], dict] = {
            (position["account_id"], position["instrument"]): position
            for position in (store.list_paper_positions() if store else [])
        }

    def connect(self) -> dict:
        return self.health_check()

    def disconnect(self) -> dict:
        return {"status": "DISCONNECTED", "adapter": "mock"}

    def health_check(self) -> dict:
        return {"status": "HEALTHY", "adapter": "mock", "live": False}

    def fetch_instruments(self) -> list[dict]:
        return [
            {"id": symbol, "venue": "MOCK"}
            for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT")
        ]

    def fetch_account(self, account_id: str) -> dict:
        positions = self.fetch_positions(account_id)
        realized = sum(float(item.get("realized_pnl", 0)) for item in positions)
        unrealized = sum(float(item.get("unrealized_pnl", 0)) for item in positions)
        exposure = sum(
            abs(float(item["quantity"]) * float(item["mark_price"]))
            for item in positions
        )
        balance = 100_000.0 + realized
        equity = balance + unrealized
        return {
            "account_id": account_id,
            "balance": balance,
            "equity": equity,
            "available_margin": max(0.0, equity - exposure),
            "daily_pnl": realized + unrealized,
            "drawdown": max(0.0, (100_000.0 - equity) / 100_000.0),
            "exposure": exposure,
            "stale": False,
        }

    def fetch_positions(self, account_id: str) -> list[dict]:
        return [
            value for (owner, _), value in self.positions.items() if owner == account_id
        ]

    def fetch_open_orders(self, account_id: str) -> list[dict]:
        return [
            value
            for value in self.orders.values()
            if value["account_id"] == account_id
            and value["state"] not in {"FILLED", "CANCELED", "REJECTED"}
        ]

    def fetch_order(self, client_order_id: str) -> dict | None:
        return self.orders.get(client_order_id)

    def fetch_fills(self, account_id: str) -> list[dict]:
        return [
            value
            for value in self.orders.values()
            if value["account_id"] == account_id and value["state"] == "FILLED"
        ]

    def mark_positions(self, quotes: list[dict]) -> int:
        prices = {quote["asset"].upper(): quote for quote in quotes}
        updated = 0
        for key, position in self.positions.items():
            asset = (
                position["instrument"].upper().removesuffix("USDT").removesuffix("USD")
            )
            quote = prices.get(asset)
            if not quote:
                continue
            mark = float(quote["price"])
            quantity = float(position["quantity"])
            average = float(position["average_price"])
            position.update(
                mark_price=mark,
                unrealized_pnl=(mark - average) * quantity,
                updated_at=quote.get("timestamp")
                or datetime.now(timezone.utc).isoformat(),
                market_provider=quote.get("provider"),
            )
            self.positions[key] = position
            if self.store:
                self.store.save_paper_position(position)
            updated += 1
        return updated

    def subscribe_market_data(self, instruments: list[str]) -> dict:
        return {"subscribed": instruments, "adapter": "mock"}

    def subscribe_user_events(self, account_id: str) -> dict:
        return {"subscribed": account_id, "adapter": "mock"}

    def submit_order(self, order: dict) -> dict:
        existing = self.orders.get(order["client_order_id"])
        if existing:
            return existing
        immediate = bool(order.get("fill_immediately"))
        filled_quantity = float(order["quantity"]) if immediate else 0.0
        accepted = {
            **order,
            "exchange_order_id": f"mock-{uuid.uuid4().hex[:16]}",
            "state": "FILLED" if immediate else "ACCEPTED",
            "filled_quantity": filled_quantity,
            "remaining_quantity": max(0.0, float(order["quantity"]) - filled_quantity),
            "average_price": float(order.get("mark_price", 0)) if immediate else None,
        }
        self.orders[order["client_order_id"]] = accepted
        if immediate:
            key = (order["account_id"], order["instrument"])
            current = self.positions.get(
                key,
                {
                    "quantity": 0.0,
                    "average_price": accepted["average_price"],
                    "realized_pnl": 0.0,
                },
            )
            signed = filled_quantity if order["side"] == "BUY" else -filled_quantity
            old_quantity = float(current["quantity"])
            old_average = float(current.get("average_price", accepted["average_price"]))
            fill_price = float(accepted["average_price"])
            net = old_quantity + signed
            same_direction = old_quantity == 0 or old_quantity * signed > 0
            if same_direction and net:
                average_price = (
                    abs(old_quantity) * old_average + abs(signed) * fill_price
                ) / abs(net)
                realized_pnl = float(current.get("realized_pnl", 0))
            else:
                closed = min(abs(old_quantity), abs(signed))
                realized_pnl = float(current.get("realized_pnl", 0)) + closed * (
                    fill_price - old_average
                ) * (1 if old_quantity > 0 else -1)
                average_price = fill_price if old_quantity * net < 0 else old_average
            position = {
                "account_id": order["account_id"],
                "instrument": order["instrument"],
                "quantity": net,
                "side": "LONG" if net > 0 else "SHORT" if net < 0 else "FLAT",
                "average_price": average_price,
                "mark_price": fill_price,
                "unrealized_pnl": 0.0,
                "realized_pnl": realized_pnl,
                "leverage": order.get("leverage", 1),
                "mode": order.get("mode", "PAPER"),
                "strategy_id": order.get("strategy_id"),
                "run_id": order.get("run_id"),
                "updated_at": order.get("source_timestamp") or order.get("created_at"),
            }
            self.positions[key] = position
            if self.store:
                self.store.save_paper_position(position)
        return accepted

    def cancel_order(self, account_id: str, client_order_id: str) -> dict:
        order = self.orders.get(client_order_id)
        if not order or order["account_id"] != account_id:
            return {"client_order_id": client_order_id, "state": "UNKNOWN"}
        order["state"] = "CANCELED"
        return order

    def cancel_all_orders(self, account_id: str) -> list[dict]:
        return [
            self.cancel_order(account_id, order["client_order_id"])
            for order in self.fetch_open_orders(account_id)
        ]

    def reconcile(self, account_id: str) -> dict:
        return {
            "account": self.fetch_account(account_id),
            "positions": self.fetch_positions(account_id),
            "open_orders": self.fetch_open_orders(account_id),
            "fills": self.fetch_fills(account_id),
        }
