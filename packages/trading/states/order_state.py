from __future__ import annotations

from packages.trading.domain.enums import OrderState


TRANSITIONS = {
    OrderState.CREATED: {OrderState.PREPARED, OrderState.REJECTED},
    OrderState.PREPARED: {
        OrderState.SUBMITTING,
        OrderState.REJECTED,
        OrderState.CANCELED,
    },
    OrderState.SUBMITTING: {
        OrderState.SUBMITTED,
        OrderState.UNKNOWN,
        OrderState.REJECTED,
    },
    OrderState.SUBMITTED: {
        OrderState.ACCEPTED,
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCEL_PENDING,
        OrderState.UNKNOWN,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    },
    OrderState.ACCEPTED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCEL_PENDING,
        OrderState.UNKNOWN,
        OrderState.EXPIRED,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCEL_PENDING,
        OrderState.UNKNOWN,
    },
    OrderState.CANCEL_PENDING: {
        OrderState.CANCELED,
        OrderState.FILLED,
        OrderState.UNKNOWN,
    },
    OrderState.UNKNOWN: {
        OrderState.RECONCILIATION_REQUIRED,
        OrderState.ACCEPTED,
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
    },
    OrderState.RECONCILIATION_REQUIRED: {
        OrderState.ACCEPTED,
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
    },
    OrderState.FILLED: set(),
    OrderState.CANCELED: set(),
    OrderState.REJECTED: set(),
    OrderState.EXPIRED: set(),
}


class InvalidOrderTransition(RuntimeError):
    pass


def transition_order(current: OrderState | str, target: OrderState | str) -> OrderState:
    before = OrderState(current)
    after = OrderState(target)
    if after not in TRANSITIONS[before]:
        raise InvalidOrderTransition(
            f"Invalid order transition: {before.value} -> {after.value}"
        )
    return after
