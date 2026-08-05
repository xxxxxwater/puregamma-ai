from __future__ import annotations

import time
import uuid
from collections import defaultdict

from packages.trading.states.order_state import transition_order


def apply_transition(store, current: dict, state: str, **updates) -> dict:
    """Validate and append one journal transition; raises on illegal transitions."""
    transition_order(current["state"], state)
    result = {
        **current,
        **updates,
        "state": state,
        "sequence": int(current["sequence"]) + 1,
    }
    result["idempotency_key"] = (
        updates.get("idempotency_key")
        or f"{current['client_order_id']}:{result['sequence']}:{state}"
    )
    if "filled_quantity" in updates:
        result["remaining_quantity"] = max(
            0.0, float(result["quantity"]) - float(updates["filled_quantity"])
        )
    store.append_order(result)
    return result


class TokenBucket:
    def __init__(self, capacity: int = 20, refill_per_second: float = 2.0):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_per_second = refill_per_second
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        self.tokens = min(
            self.capacity,
            self.tokens + (now - self.last_refill) * self.refill_per_second,
        )
        self.last_refill = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


class RuntimeExecutionGateway:
    def __init__(self, store, exchange, risk):
        self.store = store
        self.exchange = exchange
        self.risk = risk
        self.buckets: dict[str, TokenBucket] = defaultdict(TokenBucket)
        self.cancel_attempts: dict[str, int] = defaultdict(int)

    def submit(self, request: dict) -> dict:
        client_order_id = (
            request.get("client_order_id") or f"pg-{uuid.uuid4().hex[:20]}"
        )
        existing = self.store.latest_order(client_order_id)
        if existing:
            return {**existing, "idempotent": True}
        created = {
            **request,
            "client_order_id": client_order_id,
            "sequence": 1,
            "state": "CREATED",
            "filled_quantity": 0.0,
            "remaining_quantity": request["quantity"],
            "idempotency_key": f"{request['idempotency_key']}:created",
        }
        self.store.append_order(created)
        decision = self.risk.evaluate(
            request,
            request.get("risk_policy", {}),
            self.exchange.fetch_account(request["account_id"]),
        )
        if decision["decision"] != "ALLOW":
            rejected = self._next(created, "REJECTED", decision=decision)
            return {**rejected, "risk_decision": decision}
        prepared = self._next(created, "PREPARED")
        if not self.buckets[request["account_id"]].consume():
            return self._next(prepared, "REJECTED", error="RUNTIME_RATE_LIMIT")
        submitting = self._next(prepared, "SUBMITTING")
        try:
            response = self.exchange.submit_order(
                {**request, "client_order_id": client_order_id}
            )
        except Exception as exc:
            self.risk.pause_opening_accounts.add(request["account_id"])
            return self._next(submitting, "UNKNOWN", error=str(exc)[:240])
        submitted = self._next(
            submitting, "SUBMITTED", exchange_order_id=response.get("exchange_order_id")
        )
        extras = {"shadow": True} if response.get("shadow") else {}
        accepted = self._next(
            submitted,
            response.get("state", "ACCEPTED"),
            exchange_order_id=response.get("exchange_order_id"),
            filled_quantity=float(response.get("filled_quantity", 0)),
            average_price=response.get("average_price"),
            **extras,
        )
        return {**accepted, "risk_decision": decision}

    def cancel(
        self, account_id: str, client_order_id: str, idempotency_key: str
    ) -> dict:
        current = self.store.latest_order(client_order_id)
        if not current:
            return {"client_order_id": client_order_id, "state": "UNKNOWN"}
        self.cancel_attempts[client_order_id] += 1
        if self.cancel_attempts[client_order_id] > 3:
            return {**current, "error": "CANCEL_STORM_BLOCKED"}
        pending = self._next(current, "CANCEL_PENDING", idempotency_key=idempotency_key)
        response = self.exchange.cancel_order(account_id, client_order_id)
        result = self._next(pending, response.get("state", "UNKNOWN"))
        if result["state"] == "UNKNOWN":
            self.risk.pause_opening_accounts.add(account_id)
        return result

    def _next(self, current: dict, state: str, **updates) -> dict:
        return apply_transition(self.store, current, state, **updates)
