from __future__ import annotations


class DisabledLiveExchangeAdapter:
    """Status-only contract for adapters intentionally disabled in phase one."""

    name = "unconfigured"

    def __init__(self, configured: bool = False):
        self.configured = configured

    def connect(self) -> dict:
        return self.health_check()

    def disconnect(self) -> dict:
        return {"adapter": self.name, "status": "DISCONNECTED"}

    def health_check(self) -> dict:
        return {
            "adapter": self.name,
            "status": "LIVE_DISABLED" if self.configured else "NEEDS_CREDENTIALS",
            "configured": self.configured,
            "live": False,
            "orders": False,
            "withdrawal": False,
            "transfer": False,
        }

    def _disabled(self):
        raise RuntimeError(f"{self.name} order execution is disabled in phase one")

    def fetch_instruments(self) -> list[dict]:
        return []

    def fetch_account(self, account_id: str) -> dict:
        return {"account_id": account_id, "status": "UNAVAILABLE"}

    def fetch_positions(self, account_id: str) -> list[dict]:
        return []

    def fetch_open_orders(self, account_id: str) -> list[dict]:
        return []

    def fetch_order(self, client_order_id: str) -> dict | None:
        return None

    def fetch_fills(self, account_id: str) -> list[dict]:
        return []

    def subscribe_market_data(self, instruments: list[str]) -> dict:
        return {"subscribed": [], "status": "DISABLED"}

    def subscribe_user_events(self, account_id: str) -> dict:
        return {"subscribed": None, "status": "DISABLED"}

    def submit_order(self, order: dict) -> dict:
        return self._disabled()

    def cancel_order(self, account_id: str, client_order_id: str) -> dict:
        return self._disabled()

    def cancel_all_orders(self, account_id: str) -> list[dict]:
        return self._disabled()

    def reconcile(self, account_id: str) -> dict:
        return self._disabled()


class UnavailableAdapter(DisabledLiveExchangeAdapter):
    """Fail-closed adapter for venue/environment pairs without a registered adapter.

    Never silently falls back to mock execution: every order-path call raises
    with the explicit unavailability reason, and health reports UNAVAILABLE.
    """

    name = "unavailable"

    def __init__(self, reason: str, *, venue: str = "UNKNOWN", environment: str = "UNKNOWN"):
        super().__init__(configured=False)
        self.reason = reason
        self.venue = venue
        self.environment = environment

    def health_check(self) -> dict:
        return {
            "adapter": self.name,
            "venue": self.venue,
            "environment": self.environment,
            "status": "UNAVAILABLE",
            "reason": self.reason,
            "configured": False,
            "live": False,
            "orders": False,
            "withdrawal": False,
            "transfer": False,
        }

    def _disabled(self):
        raise RuntimeError(f"Exchange adapter unavailable: {self.reason}")
