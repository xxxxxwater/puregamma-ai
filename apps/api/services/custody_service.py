"""Custody domain service (P0-10b): real custody as an independent domain.

This is NOT TradingAccount. A CustodyAccount is a venue custody account
(testnet/sandbox first); CustodySubAccount is the per-user, per-asset
sub-ledger with available/frozen balances; CustodyLedgerEntry is the
append-only audit trail for every balance mutation.

Invariants:
- Money is always ``Decimal`` (Numeric(38,18)); never float math.
- Every mutation is idempotent via an explicit ``idempotency_key``.
- Every mutation runs in the caller's transaction and locks the sub-account
  row (``with_for_update``) before reading/modifying balances.
- The ledger is append-only: update/delete raise (listeners registered at
  module import time, mirroring the CreditLedger guard).
- No fake addresses or balances: without provider credentials the account is
  ``UNCONFIGURED`` with a NULL deposit_address; reconciliation without an
  external balance reports ``UNAVAILABLE``, never a fake MATCH.

Execution wiring (quote-asset-only accounting):
- A trading account is custody-linked when one of its ExchangeConnection rows
  carries ``metadata_json["custody_account_id"]``. Unlinked accounts keep the
  previous behavior exactly.
- Custody accounting is kept in the quote asset (the trading account's
  ``base_currency``, e.g. USD/USDT). Base-asset quantities remain the trading
  runtime's job (position snapshots); they are not double-tracked here.
- BUY order submission freezes the quote notional (``freeze``). A BUY fill
  debits the frozen hold (``trade_debit`` — cash left custody to acquire the
  base asset). A SELL fill credits the quote proceeds (``trade_credit``).
  A REJECTED BUY releases the hold (``unfreeze``). SELL orders take no hold:
  in quote-only accounting there is no base balance to freeze.
- A confirmed withdrawal debits the frozen hold via a ``trade_debit`` entry
  (funds left custody); a failed/rejected withdrawal releases the hold back
  to available via ``withdrawal_release``.
"""

from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import event
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import (
    CustodyAccount,
    CustodyDeposit,
    CustodyLedgerEntry,
    CustodyReconciliation,
    CustodySubAccount,
    CustodyWithdrawal,
    ExchangeConnection,
    utcnow,
)

DEFAULT_VENUE = "binance_testnet"
DEFAULT_ENVIRONMENT = "testnet"
DEFAULT_QUOTE_ASSET = "USD"

# ExchangeConnection.metadata_json key linking a trading account to custody.
CUSTODY_LINK_KEY = "custody_account_id"

FILLED_STATES = {"FILLED", "PARTIAL", "PARTIALLY_FILLED"}

_WITHDRAWAL_TRANSITIONS = {
    "intent": {"approved", "rejected"},
    "approved": {"submitted", "rejected"},
    "submitted": {"confirmed", "failed"},
    "confirmed": set(),
    "failed": set(),
    "rejected": set(),
}

_ETH_ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")
_BTC_ADDRESS = re.compile(
    r"^(bc1[a-z0-9]{25,59}|tb1[a-z0-9]{25,59}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|[mn2][a-km-zA-HJ-NP-Z1-9]{25,34})$"
)
_ADDRESS_PATTERNS = {
    "BTC": _BTC_ADDRESS,
    "ETH": _ETH_ADDRESS,
    "USDT": _ETH_ADDRESS,  # ERC20
    "USDC": _ETH_ADDRESS,  # ERC20
}


class CustodyError(RuntimeError):
    pass


class InsufficientCustodyBalance(CustodyError):
    pass


class InvalidWithdrawalAddress(CustodyError):
    pass


class UnsupportedWithdrawalAsset(CustodyError):
    pass


class InvalidWithdrawalTransition(CustodyError):
    pass


# --------------------------------------------------------------------------
# Append-only ledger guard. Registered at import time (same pattern as the
# CreditLedger guard in packages/database/models.py).
# --------------------------------------------------------------------------


def _prevent_custody_ledger_mutation(*_args, **_kwargs) -> None:
    raise RuntimeError("CustodyLedgerEntry is append-only")


event.listen(CustodyLedgerEntry, "before_update", _prevent_custody_ledger_mutation)
event.listen(CustodyLedgerEntry, "before_delete", _prevent_custody_ledger_mutation)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _dec(value) -> Decimal:
    """Coerce an ORM Numeric / int / str to Decimal without float artifacts."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _positive_amount(amount) -> Decimal:
    value = _dec(amount)
    if value <= 0:
        raise ValueError("Custody amounts must be positive")
    return value


def provider_credentials_configured(settings=None) -> bool:
    """Boolean only — credential material itself is never exposed."""
    current = settings or get_settings()
    return bool(
        getattr(current, "custody_provider_api_key", "")
        and getattr(current, "custody_provider_api_secret", "")
    )


def validate_withdrawal_address(asset: str, address: str) -> None:
    pattern = _ADDRESS_PATTERNS.get(asset.upper())
    if pattern is None:
        raise UnsupportedWithdrawalAsset(f"Unsupported withdrawal asset: {asset}")
    if not pattern.match(address or ""):
        raise InvalidWithdrawalAddress(f"Invalid {asset.upper()} withdrawal address")


# --------------------------------------------------------------------------
# Account / sub-account provisioning
# --------------------------------------------------------------------------


def get_or_create_custody_account(
    db: Session,
    venue: str = DEFAULT_VENUE,
    environment: str = DEFAULT_ENVIRONMENT,
) -> CustodyAccount:
    """Singleton-per-(venue, environment) custody account row.

    Without provider credentials the account is UNCONFIGURED and the deposit
    address stays NULL — a fake address is never shown. With credentials the
    account is ACTIVE; the deposit address is populated only from the provider
    (out-of-band provisioning stores it in metadata_json["deposit_address"]),
    never invented.
    """
    account = (
        db.query(CustodyAccount)
        .filter_by(venue=venue, environment=environment)
        .one_or_none()
    )
    if account:
        return account
    configured = provider_credentials_configured()
    account = CustodyAccount(
        venue=venue,
        environment=environment,
        status="ACTIVE" if configured else "UNCONFIGURED",
        deposit_address=None,
        provider_ref=None,
        metadata_json={},
    )
    db.add(account)
    db.flush()
    return account


def ensure_sub_account(
    db: Session, account: CustodyAccount, user_id: str, asset: str
) -> CustodySubAccount:
    asset = asset.upper()
    sub_account = (
        db.query(CustodySubAccount)
        .filter_by(custody_account_id=account.id, user_id=user_id, asset=asset)
        .one_or_none()
    )
    if sub_account:
        return sub_account
    sub_account = CustodySubAccount(
        custody_account_id=account.id,
        user_id=user_id,
        asset=asset,
        available=Decimal("0"),
        frozen=Decimal("0"),
    )
    db.add(sub_account)
    db.flush()
    return sub_account


def _lock_sub_account(db: Session, sub_account_id: str) -> CustodySubAccount:
    return (
        db.query(CustodySubAccount)
        .filter_by(id=sub_account_id)
        .with_for_update()
        .one()
    )


def _append_entry(
    db: Session,
    sub_account: CustodySubAccount,
    entry_type: str,
    amount: Decimal,
    ref: tuple[str | None, str | None] | None,
    idempotency_key: str,
) -> CustodyLedgerEntry:
    existing = (
        db.query(CustodyLedgerEntry)
        .filter_by(idempotency_key=idempotency_key)
        .one_or_none()
    )
    if existing:
        return existing
    entry = CustodyLedgerEntry(
        sub_account_id=sub_account.id,
        entry_type=entry_type,
        amount=amount,
        available_after=_dec(sub_account.available),
        frozen_after=_dec(sub_account.frozen),
        ref_type=ref[0] if ref else None,
        ref_id=ref[1] if ref else None,
        idempotency_key=idempotency_key,
    )
    db.add(entry)
    db.flush()
    return entry


def _ledger_op(
    db: Session,
    sub_account: CustodySubAccount,
    entry_type: str,
    amount,
    ref: tuple[str | None, str | None] | None,
    idempotency_key: str,
    mutate,
) -> CustodyLedgerEntry:
    """Idempotent, row-locked balance mutation + append-only ledger entry."""
    value = _positive_amount(amount)
    existing = (
        db.query(CustodyLedgerEntry)
        .filter_by(idempotency_key=idempotency_key)
        .one_or_none()
    )
    if existing:
        return existing
    locked = _lock_sub_account(db, sub_account.id)
    # Re-check under the row lock to close the optimistic-lookup race.
    existing = (
        db.query(CustodyLedgerEntry)
        .filter_by(idempotency_key=idempotency_key)
        .one_or_none()
    )
    if existing:
        return existing
    mutate(locked, value)
    db.flush()
    return _append_entry(db, locked, entry_type, value, ref, idempotency_key)


# --------------------------------------------------------------------------
# Core ledger operations
# --------------------------------------------------------------------------


def credit_deposit(
    db: Session,
    sub_account: CustodySubAccount,
    amount,
    tx_ref: str,
    external_ref: str,
) -> CustodyDeposit:
    """Credit a confirmed deposit. Repeating the same external_ref returns the
    existing deposit without a second credit."""
    value = _positive_amount(amount)
    existing = (
        db.query(CustodyDeposit).filter_by(external_ref=external_ref).one_or_none()
    )
    if existing:
        return existing
    locked = _lock_sub_account(db, sub_account.id)
    existing = (
        db.query(CustodyDeposit).filter_by(external_ref=external_ref).one_or_none()
    )
    if existing:
        return existing
    deposit = CustodyDeposit(
        sub_account_id=locked.id,
        asset=locked.asset,
        amount=value,
        tx_ref=tx_ref,
        confirmations=0,
        status="credited",
        external_ref=external_ref,
        confirmed_at=utcnow(),
    )
    db.add(deposit)
    db.flush()
    locked.available = _dec(locked.available) + value
    db.flush()
    _append_entry(
        db,
        locked,
        "deposit_confirm",
        value,
        ("custody_deposit", deposit.id),
        f"custody:deposit:{external_ref}",
    )
    return deposit


def freeze(
    db: Session,
    sub_account: CustodySubAccount,
    amount,
    ref: tuple[str | None, str | None] | None = None,
    *,
    idempotency_key: str,
) -> CustodyLedgerEntry:
    """Move available -> frozen (order/withdrawal hold)."""

    def _mutate(locked: CustodySubAccount, value: Decimal) -> None:
        if _dec(locked.available) < value:
            raise InsufficientCustodyBalance(
                f"Insufficient available custody balance: required {value}, available {locked.available}"
            )
        locked.available = _dec(locked.available) - value
        locked.frozen = _dec(locked.frozen) + value

    return _ledger_op(db, sub_account, "freeze", amount, ref, idempotency_key, _mutate)


def unfreeze(
    db: Session,
    sub_account: CustodySubAccount,
    amount,
    ref: tuple[str | None, str | None] | None = None,
    *,
    idempotency_key: str,
) -> CustodyLedgerEntry:
    """Move frozen -> available (hold released)."""

    def _mutate(locked: CustodySubAccount, value: Decimal) -> None:
        if _dec(locked.frozen) < value:
            raise InsufficientCustodyBalance(
                f"Insufficient frozen custody balance: required {value}, frozen {locked.frozen}"
            )
        locked.frozen = _dec(locked.frozen) - value
        locked.available = _dec(locked.available) + value

    return _ledger_op(db, sub_account, "unfreeze", amount, ref, idempotency_key, _mutate)


def trade_debit(
    db: Session,
    sub_account: CustodySubAccount,
    amount,
    ref: tuple[str | None, str | None] | None = None,
    *,
    idempotency_key: str,
) -> CustodyLedgerEntry:
    """Debit from the frozen hold: funds permanently left the cash balance
    (BUY fill cost, confirmed withdrawal)."""

    def _mutate(locked: CustodySubAccount, value: Decimal) -> None:
        if _dec(locked.frozen) < value:
            raise InsufficientCustodyBalance(
                f"Insufficient frozen custody balance: required {value}, frozen {locked.frozen}"
            )
        locked.frozen = _dec(locked.frozen) - value

    return _ledger_op(db, sub_account, "trade_debit", amount, ref, idempotency_key, _mutate)


def trade_credit(
    db: Session,
    sub_account: CustodySubAccount,
    amount,
    ref: tuple[str | None, str | None] | None = None,
    *,
    idempotency_key: str,
) -> CustodyLedgerEntry:
    """Credit fill proceeds (SELL) to available."""

    def _mutate(locked: CustodySubAccount, value: Decimal) -> None:
        locked.available = _dec(locked.available) + value

    return _ledger_op(db, sub_account, "trade_credit", amount, ref, idempotency_key, _mutate)


# --------------------------------------------------------------------------
# Withdrawals
# --------------------------------------------------------------------------


def request_withdrawal(
    db: Session,
    sub_account: CustodySubAccount,
    asset: str,
    amount,
    address: str,
    idempotency_key: str,
) -> CustodyWithdrawal:
    """Create a withdrawal intent and hold the funds (available -> frozen).
    The same idempotency key always returns the original withdrawal."""
    value = _positive_amount(amount)
    validate_withdrawal_address(asset, address)
    existing = (
        db.query(CustodyWithdrawal)
        .filter_by(idempotency_key=idempotency_key)
        .one_or_none()
    )
    if existing:
        return existing
    locked = _lock_sub_account(db, sub_account.id)
    existing = (
        db.query(CustodyWithdrawal)
        .filter_by(idempotency_key=idempotency_key)
        .one_or_none()
    )
    if existing:
        return existing
    withdrawal = CustodyWithdrawal(
        sub_account_id=locked.id,
        asset=asset.upper(),
        amount=value,
        address=address,
        status="intent",
        idempotency_key=idempotency_key,
    )
    db.add(withdrawal)
    db.flush()

    def _hold(locked_row: CustodySubAccount, held: Decimal) -> None:
        if _dec(locked_row.available) < held:
            raise InsufficientCustodyBalance(
                f"Insufficient available custody balance: required {held}, available {locked_row.available}"
            )
        locked_row.available = _dec(locked_row.available) - held
        locked_row.frozen = _dec(locked_row.frozen) + held

    _hold(locked, value)
    db.flush()
    _append_entry(
        db,
        locked,
        "withdrawal_hold",
        value,
        ("custody_withdrawal", withdrawal.id),
        f"custody:withdrawal-hold:{idempotency_key}",
    )
    return withdrawal


def mark_withdrawal_status(
    db: Session,
    withdrawal: CustodyWithdrawal,
    status: str,
    tx_ref: str | None = None,
    error: str | None = None,
) -> CustodyWithdrawal:
    """Transition a withdrawal along the legal map
    intent -> approved -> submitted -> confirmed | failed | rejected.
    failed/rejected release the hold back to available; confirmed debits the
    frozen hold (funds left custody). Repeating the current status is a no-op.
    """
    status = status.lower()
    if withdrawal.status == status:
        return withdrawal
    if status not in _WITHDRAWAL_TRANSITIONS.get(withdrawal.status, set()):
        raise InvalidWithdrawalTransition(
            f"Withdrawal cannot transition {withdrawal.status} -> {status}"
        )
    locked = _lock_sub_account(db, withdrawal.sub_account_id)
    amount = _dec(withdrawal.amount)
    withdrawal.status = status
    if tx_ref is not None:
        withdrawal.tx_ref = tx_ref
    if error is not None:
        withdrawal.error = error
    db.flush()
    if status in {"failed", "rejected"}:
        if _dec(locked.frozen) < amount:
            raise InsufficientCustodyBalance(
                f"Insufficient frozen custody balance to release: required {amount}, frozen {locked.frozen}"
            )
        locked.frozen = _dec(locked.frozen) - amount
        locked.available = _dec(locked.available) + amount
        db.flush()
        _append_entry(
            db,
            locked,
            "withdrawal_release",
            amount,
            ("custody_withdrawal", withdrawal.id),
            f"custody:withdrawal-release:{withdrawal.idempotency_key}",
        )
    elif status == "confirmed":
        if _dec(locked.frozen) < amount:
            raise InsufficientCustodyBalance(
                f"Insufficient frozen custody balance to settle: required {amount}, frozen {locked.frozen}"
            )
        locked.frozen = _dec(locked.frozen) - amount
        db.flush()
        # Funds left custody: debit from the frozen hold.
        _append_entry(
            db,
            locked,
            "trade_debit",
            amount,
            ("custody_withdrawal", withdrawal.id),
            f"custody:withdrawal-debit:{withdrawal.idempotency_key}",
        )
    return withdrawal


# --------------------------------------------------------------------------
# Reconciliation and views
# --------------------------------------------------------------------------


def reconcile(
    db: Session,
    account: CustodyAccount,
    asset: str,
    external_balance,
) -> CustodyReconciliation:
    """Compare the sum of sub-account balances (available + frozen) against
    the external venue balance. external_balance=None -> UNAVAILABLE (never a
    fake match); a non-zero difference -> MISMATCH; otherwise MATCH."""
    asset = asset.upper()
    sub_accounts = (
        db.query(CustodySubAccount)
        .filter_by(custody_account_id=account.id, asset=asset)
        .all()
    )
    local_available = sum((_dec(row.available) for row in sub_accounts), Decimal("0"))
    local_frozen = sum((_dec(row.frozen) for row in sub_accounts), Decimal("0"))
    if external_balance is None:
        status = "UNAVAILABLE"
        external = None
        difference = None
    else:
        external = _dec(external_balance)
        difference = external - (local_available + local_frozen)
        status = "MATCH" if difference == 0 else "MISMATCH"
    record = CustodyReconciliation(
        custody_account_id=account.id,
        asset=asset,
        local_available=local_available,
        local_frozen=local_frozen,
        external_balance=external,
        difference=difference,
        status=status,
        details_json={
            "sub_accounts": len(sub_accounts),
            "venue": account.venue,
            "environment": account.environment,
        },
    )
    db.add(record)
    db.flush()
    return record


def sub_account_view(db: Session, user_id: str) -> list[dict]:
    """All of a user's sub-accounts with their custody account context.
    Never includes secrets or provider credentials."""
    rows = (
        db.query(CustodySubAccount, CustodyAccount)
        .join(CustodyAccount, CustodySubAccount.custody_account_id == CustodyAccount.id)
        .filter(CustodySubAccount.user_id == user_id)
        .order_by(CustodySubAccount.asset.asc())
        .all()
    )
    return [
        {
            "sub_account_id": sub.id,
            "asset": sub.asset,
            "available": _dec(sub.available),
            "frozen": _dec(sub.frozen),
            "account": {
                "id": account.id,
                "venue": account.venue,
                "environment": account.environment,
                "status": account.status,
            },
        }
        for sub, account in rows
    ]


# --------------------------------------------------------------------------
# Execution wiring helpers (custody-linked trading accounts only)
# --------------------------------------------------------------------------


def custody_link_for_account(db: Session, trading_account_id: str) -> CustodyAccount | None:
    """Resolve the custody account linked to a trading account via
    ExchangeConnection.metadata_json["custody_account_id"]; None when the
    account is not custody-enabled (behavior unchanged for unlinked accounts)."""
    connections = (
        db.query(ExchangeConnection).filter_by(account_id=trading_account_id).all()
    )
    for connection in connections:
        custody_account_id = (connection.metadata_json or {}).get(CUSTODY_LINK_KEY)
        if custody_account_id:
            account = db.get(CustodyAccount, custody_account_id)
            if account is not None:
                return account
    return None


def _filled_notional(filled_quantity, average_price, quantity, notional) -> Decimal:
    filled = _dec(filled_quantity)
    if average_price is not None:
        return filled * _dec(average_price)
    total = _dec(quantity)
    if total > 0:
        return _dec(notional) * filled / total
    return Decimal("0")


def apply_order_freeze(
    db: Session,
    *,
    trading_account,
    user_id: str,
    order_ref: str,
    side: str,
    notional,
    quote_asset: str | None = None,
) -> bool:
    """Freeze the quote notional for a BUY order at submission time.

    Returns False when the trading account is not custody-linked (behavior
    unchanged) or the hold amount is zero. Raises InsufficientCustodyBalance
    when the user cannot cover the hold.
    """
    account = custody_link_for_account(db, trading_account.id)
    if account is None:
        return False
    value = _dec(notional or 0)
    if side.upper() != "BUY" or value <= 0:
        return True  # custody-linked, but quote-only holds apply to BUYs
    asset = (quote_asset or getattr(trading_account, "base_currency", None) or DEFAULT_QUOTE_ASSET).upper()
    sub_account = ensure_sub_account(db, account, user_id, asset)
    freeze(
        db,
        sub_account,
        value,
        ("order", order_ref),
        idempotency_key=f"custody:freeze:{order_ref}",
    )
    return True


def apply_fill_settlement(
    db: Session,
    *,
    trading_account,
    user_id: str,
    fill_ref: str,
    side: str,
    state: str,
    quantity,
    filled_quantity,
    average_price,
    notional,
    quote_asset: str | None = None,
) -> bool:
    """Settle a fill into custody: BUY debits the frozen hold, SELL credits
    the quote proceeds. Idempotent on fill_ref (order/fill id derived)."""
    account = custody_link_for_account(db, trading_account.id)
    if account is None:
        return False
    if state not in FILLED_STATES or _dec(filled_quantity or 0) <= 0:
        return True
    asset = (quote_asset or getattr(trading_account, "base_currency", None) or DEFAULT_QUOTE_ASSET).upper()
    sub_account = ensure_sub_account(db, account, user_id, asset)
    filled_notional = _filled_notional(filled_quantity, average_price, quantity, notional)
    if filled_notional <= 0:
        return True
    if side.upper() == "BUY":
        locked = _lock_sub_account(db, sub_account.id)
        debit = min(filled_notional, _dec(locked.frozen))
        if debit > 0:
            trade_debit(
                db,
                locked,
                debit,
                ("fill", fill_ref),
                idempotency_key=f"custody:debit:{fill_ref}",
            )
    else:
        trade_credit(
            db,
            sub_account,
            filled_notional,
            ("fill", fill_ref),
            idempotency_key=f"custody:credit:{fill_ref}",
        )
    return True


def release_order_freeze(
    db: Session,
    *,
    trading_account,
    user_id: str,
    order_ref: str,
    side: str,
    notional,
    quote_asset: str | None = None,
) -> bool:
    """Release a BUY hold when the order was rejected before any fill."""
    account = custody_link_for_account(db, trading_account.id)
    if account is None:
        return False
    value = _dec(notional or 0)
    if side.upper() != "BUY" or value <= 0:
        return True
    asset = (quote_asset or getattr(trading_account, "base_currency", None) or DEFAULT_QUOTE_ASSET).upper()
    sub_account = ensure_sub_account(db, account, user_id, asset)
    locked = _lock_sub_account(db, sub_account.id)
    release = min(value, _dec(locked.frozen))
    if release > 0:
        unfreeze(
            db,
            locked,
            release,
            ("order", order_ref),
            idempotency_key=f"custody:unfreeze:{order_ref}",
        )
    return True
