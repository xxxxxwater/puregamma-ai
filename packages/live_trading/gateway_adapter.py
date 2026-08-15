"""Execution Gateway adapter layer.

Only the Trading Control Plane talks to this layer; Harness, Agent, Memory,
and mobile/web clients can never reach it. Two implementations:

- ``MockExecutionGateway`` (default): always healthy-but-refusing. It is used
  until a real broker adapter is provisioned, and it NEVER fakes a fill.
- ``NautilusExecutionGateway``: delegates to the Nautilus Runtime
  (submit_order / cancel_order / reconcile) with ``mode="live"`` payloads.

Order-state rules enforced by the control plane on top of this layer:
- a submit timeout never triggers a blind retry;
- an UNKNOWN state triggers a gateway query, not another submit;
- server time is authoritative (clients never supply timestamps).
"""

from __future__ import annotations

from typing import Any, Protocol

from apps.api.config import get_settings
from packages.trading.runtime_client import NautilusRuntimeClient, RuntimeUnavailable


class GatewayError(RuntimeError):
    pass


class GatewayUnavailable(GatewayError):
    pass


class GatewayOrderUnknown(GatewayError):
    """Raised when a submit timed out and the gateway cannot confirm state."""


class ExecutionGateway(Protocol):
    name: str

    def health(self) -> dict[str, Any]: ...

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def query_order(self, client_order_id: str, account_id: str) -> dict[str, Any]: ...

    def cancel_order(self, client_order_id: str, account_id: str) -> dict[str, Any]: ...

    def account_balances(self, account_id: str) -> dict[str, Any]: ...

    def positions(self, account_id: str) -> list[dict[str, Any]]: ...


class MockExecutionGateway:
    """Honest mock: reports DISABLED and never invents fills or balances."""

    name = "mock"

    def health(self) -> dict[str, Any]:
        return {"status": "DISABLED", "adapter": self.name, "live": False}

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise GatewayUnavailable(
            "Execution Gateway is not configured (LIVE_TRADING_GATEWAY=mock); "
            "no real order was submitted"
        )

    def query_order(self, client_order_id: str, account_id: str) -> dict[str, Any]:
        raise GatewayOrderUnknown("No gateway configured; order state is unknown")

    def cancel_order(self, client_order_id: str, account_id: str) -> dict[str, Any]:
        raise GatewayUnavailable("No gateway configured; cancel is unavailable")

    def account_balances(self, account_id: str) -> dict[str, Any]:
        raise GatewayUnavailable("No gateway configured; balances unavailable")

    def positions(self, account_id: str) -> list[dict[str, Any]]:
        raise GatewayUnavailable("No gateway configured; positions unavailable")


class NautilusExecutionGateway:
    """Adapter onto the Nautilus Runtime / Execution Gateway service."""

    name = "nautilus"

    def __init__(self, client: NautilusRuntimeClient | None = None):
        self.client = client or NautilusRuntimeClient()

    def health(self) -> dict[str, Any]:
        try:
            return self.client.health()
        except RuntimeUnavailable as exc:
            raise GatewayUnavailable(str(exc)) from exc

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            ack = self.client.command(
                "submit_order",
                f"live:{payload.get('idempotency_key', '')}",
                {"mode": "live", **payload},
            )
        except RuntimeUnavailable as exc:
            # A transport failure during submission is UNKNOWN, never REJECTED.
            raise GatewayOrderUnknown(
                f"Submit transport failure; order state unknown: {str(exc)[:240]}"
            ) from exc
        if ack.get("state") == "UNKNOWN":
            raise GatewayOrderUnknown(ack.get("error", "Gateway returned UNKNOWN"))
        return ack

    def query_order(self, client_order_id: str, account_id: str) -> dict[str, Any]:
        try:
            ack = self.client.command(
                "reconcile",
                f"live-query:{client_order_id}",
                {"account_id": account_id},
            )
        except RuntimeUnavailable as exc:
            raise GatewayOrderUnknown(f"Query transport failure: {str(exc)[:240]}") from exc
        exchange = ack.get("exchange", {})
        open_orders = exchange.get("open_orders") or ack.get("local_open_orders") or []
        for order in open_orders:
            if order.get("client_order_id") == client_order_id:
                return {"state": order.get("state", "UNKNOWN"), "order": order}
        return {"state": "UNKNOWN", "order": None, "reason": "order not found in open orders"}

    def cancel_order(self, client_order_id: str, account_id: str) -> dict[str, Any]:
        try:
            return self.client.command(
                "cancel_order",
                f"live-cancel:{client_order_id}",
                {"account_id": account_id, "client_order_id": client_order_id},
            )
        except RuntimeUnavailable as exc:
            raise GatewayUnavailable(str(exc)) from exc

    def account_balances(self, account_id: str) -> dict[str, Any]:
        try:
            state = self.client.account_state(account_id)
        except RuntimeUnavailable as exc:
            raise GatewayUnavailable(str(exc)) from exc
        account = state.get("account", state)
        return {
            "cash": account.get("balance"),
            "equity": account.get("equity"),
            "available": account.get("available_margin"),
        }

    def positions(self, account_id: str) -> list[dict[str, Any]]:
        try:
            state = self.client.account_state(account_id)
        except RuntimeUnavailable as exc:
            raise GatewayUnavailable(str(exc)) from exc
        return state.get("positions", [])


def get_execution_gateway() -> ExecutionGateway:
    """Factory. Defaults to the mock gateway so LIVE can never accidentally
    reach a broker until ``LIVE_TRADING_GATEWAY=nautilus`` AND
    ``LIVE_TRADING_ENABLED=true`` are both set."""
    settings = get_settings()
    if (
        settings.live_trading_gateway == "nautilus"
        and settings.live_trading_enabled
        and settings.live_trading_provider
    ):
        return NautilusExecutionGateway()
    return MockExecutionGateway()
