"""Shared enums for the LIVE Trading Control Plane."""

from __future__ import annotations

from enum import Enum


class OrderSource(str, Enum):
    """Who created an order intent. The Harness may only produce ``strategy``
    suggestions; it can never attach ``live_order`` to a submission."""

    USER_CONFIRMED = "user_confirmed"
    STRATEGY = "strategy"
    ADMIN = "admin"
    SYSTEM = "system"
    # Reserved and rejected by the control plane: the Harness has no path
    # that may ever produce this source.
    LIVE_ORDER = "live_order"


class IntentStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELED = "CANCELED"


class LiveOrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


TERMINAL_ORDER_STATUSES = {
    LiveOrderStatus.FILLED,
    LiveOrderStatus.CANCELED,
    LiveOrderStatus.REJECTED,
    LiveOrderStatus.EXPIRED,
}


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class LedgerEntryType(str, Enum):
    CASH_DEPOSIT = "cash_deposit"
    CASH_WITHDRAWAL = "cash_withdrawal"
    TRADE_BUY = "trade_buy"
    TRADE_SELL = "trade_sell"
    FEE = "fee"
    FUNDING = "funding"
    DIVIDEND = "dividend"
    ADJUSTMENT = "adjustment"
    RECONCILIATION_ADJUSTMENT = "reconciliation_adjustment"


class KillSwitchScope(str, Enum):
    GLOBAL = "global"
    USER = "user"
    MANDATE = "mandate"
    CONNECTION = "connection"


class MandateEnvironment(str, Enum):
    PAPER = "paper"
    TESTNET = "testnet"
    PRODUCTION = "production"


class MandateStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ReconciliationStatus(str, Enum):
    OK = "ok"
    DISCREPANCY = "discrepancy"
    ERROR = "error"
