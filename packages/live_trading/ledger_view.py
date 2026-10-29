"""Owner-scoped, read-only views of the LIVE ledger and reconciliation.

Nothing here writes. Every read resolves the account (and optional mandate)
against the authenticated user first; a selector that names somebody else's
account or mandate is indistinguishable from one that does not exist
(``LookupError`` -> HTTP 404), so ids cannot be enumerated.

Money and quantities leave this module as plain decimal strings
(``decimal_text``, never exponent notation). A value the server does not have
is ``None`` — never ``"0"`` — and an account with no ledger rows reports
``empty`` instead of a zero balance.

Pagination is keyset on ``(created_at DESC, id DESC)``: stable under concurrent
appends (new rows land before the first page, never inside a later one) and
without OFFSET scans. The cursor is opaque to clients but carries no
authority: the ownership filter is applied on every page regardless of what
the cursor says.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from packages.database.models import (
    LedgerEntry,
    TradingAccount,
    TradingAuditLog,
    TradingMandate,
    TradingReconciliation,
)
from packages.live_trading.decimal_text import decimal_text
from packages.live_trading.enums import LedgerEntryType

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
_CURSOR_VERSION = 1
_ENTRY_TYPES = {item.value for item in LedgerEntryType}
# Keys inside reconciliation JSON that hold amounts written with ``str(Decimal)``
# (which can be ``0E-8``); they are re-rendered as plain decimal text.
_AMOUNT_KEYS = {"cash", "equity", "nav", "exchange", "ledger", "ledger_cash", "nav_cash", "delta"}
RECONCILIATION_REVIEW_ACTION = "LIVE_RECONCILIATION_REVIEWED"


class CursorError(ValueError):
    """The cursor is malformed (HTTP 400, not 500)."""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None


def encode_cursor(created_at: datetime, row_id: str) -> str:
    raw = json.dumps(
        {"v": _CURSOR_VERSION, "t": _aware(created_at).isoformat(), "id": row_id},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    if not cursor or len(cursor) > 512:
        raise CursorError("Invalid cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if not isinstance(data, dict) or data.get("v") != _CURSOR_VERSION:
            raise CursorError("Invalid cursor")
        created_at = _aware(datetime.fromisoformat(str(data["t"])))
        row_id = str(data["id"])
    except CursorError:
        raise
    except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise CursorError("Invalid cursor") from exc
    if not row_id or len(row_id) > 64:
        raise CursorError("Invalid cursor")
    return created_at, row_id


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


def resolve_account(db: Session, user_id: str, account_id: str | None) -> TradingAccount:
    """The caller's account, or ``LookupError`` (another user's id included)."""
    query = db.query(TradingAccount).filter(TradingAccount.user_id == user_id)
    if account_id:
        row = query.filter(TradingAccount.id == account_id).one_or_none()
    else:
        row = (
            query.filter(TradingAccount.status == "ACTIVE")
            .order_by(TradingAccount.created_at.asc(), TradingAccount.id.asc())
            .first()
        )
    if row is None:
        raise LookupError("Trading account not found")
    return row


def _resolve_mandate(db: Session, user_id: str, account: TradingAccount, mandate_id: str) -> TradingMandate:
    row = (
        db.query(TradingMandate)
        .filter(
            TradingMandate.id == mandate_id,
            TradingMandate.user_id == user_id,
            TradingMandate.account_id == account.id,
        )
        .one_or_none()
    )
    if row is None:
        raise LookupError("Trading mandate not found")
    return row


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_account(row: TradingAccount) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "venue": row.venue,
        "account_type": row.account_type,
        "base_currency": row.base_currency,
        "status": row.status,
    }


def serialize_entry(row: LedgerEntry) -> dict:
    return {
        "id": row.id,
        "account_id": row.account_id,
        "mandate_id": row.mandate_id,
        "entry_type": row.entry_type,
        "ref_type": row.ref_type,
        "ref_id": row.ref_id,
        "symbol": row.symbol,
        "quantity": decimal_text(row.quantity),
        "price": decimal_text(row.price),
        "amount": decimal_text(row.amount),
        "currency": row.currency,
        # Older rows may not carry a running balance; that is "not recorded",
        # not zero.
        "balance_after": decimal_text(row.balance_after),
        "trace_id": row.trace_id,
        "created_at": _iso(row.created_at),
    }


def _normalize_amounts(value):
    if isinstance(value, dict):
        return {
            key: (_plain_decimal(item) if key in _AMOUNT_KEYS else _normalize_amounts(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_amounts(item) for item in value]
    return value


def _plain_decimal(value):
    if value is None or isinstance(value, bool):
        return value
    try:
        return decimal_text(str(value))
    except Exception:
        # Not numeric (e.g. an error marker): pass through unchanged rather than
        # inventing a number.
        return value


# ---------------------------------------------------------------------------
# Ledger page
# ---------------------------------------------------------------------------


def ledger_page(
    db: Session,
    user_id: str,
    *,
    account_id: str | None = None,
    mandate_id: str | None = None,
    entry_type: str | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> dict:
    account = resolve_account(db, user_id, account_id)
    if entry_type is not None and entry_type not in _ENTRY_TYPES:
        raise ValueError("Unknown ledger entry type")
    page_size = max(1, min(int(limit), MAX_PAGE_SIZE))

    query = db.query(LedgerEntry).filter(
        LedgerEntry.account_id == account.id,
        LedgerEntry.user_id == user_id,
    )
    if mandate_id:
        mandate = _resolve_mandate(db, user_id, account, mandate_id)
        query = query.filter(LedgerEntry.mandate_id == mandate.id)
    if entry_type:
        query = query.filter(LedgerEntry.entry_type == entry_type)
    if cursor:
        after_at, after_id = decode_cursor(cursor)
        query = query.filter(
            or_(
                LedgerEntry.created_at < after_at,
                and_(LedgerEntry.created_at == after_at, LedgerEntry.id < after_id),
            )
        )
    rows = (
        query.order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .limit(page_size + 1)
        .all()
    )
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return {
        "account": serialize_account(account),
        "entries": [serialize_entry(row) for row in rows],
        "next_cursor": next_cursor,
        "limit": page_size,
    }


# ---------------------------------------------------------------------------
# Reconciliation view
# ---------------------------------------------------------------------------


def ledger_summary(db: Session, user_id: str, account_id: str) -> dict:
    """Ledger-derived balances per currency.

    Amounts are only summed within one currency (a BTC fee is not USD cash).
    An account with no rows is ``empty`` with no balances — not a zero.
    """
    base = (LedgerEntry.account_id == account_id, LedgerEntry.user_id == user_id)
    count, last_at = db.query(func.count(LedgerEntry.id), func.max(LedgerEntry.created_at)).filter(*base).one()
    balances = (
        db.query(LedgerEntry.currency, func.sum(LedgerEntry.amount))
        .filter(*base)
        .group_by(LedgerEntry.currency)
        .order_by(LedgerEntry.currency.asc())
        .all()
    )
    positions = (
        db.query(LedgerEntry.symbol, func.sum(LedgerEntry.quantity))
        .filter(
            *base,
            LedgerEntry.entry_type.in_(["trade_buy", "trade_sell"]),
            LedgerEntry.symbol.isnot(None),
        )
        .group_by(LedgerEntry.symbol)
        .order_by(LedgerEntry.symbol.asc())
        .all()
    )
    return {
        "entry_count": int(count or 0),
        "empty": not count,
        "last_entry_at": _iso(last_at) if last_at else None,
        "balances": [
            {"currency": currency, "amount": decimal_text(amount)}
            for currency, amount in balances
            if amount is not None
        ],
        "positions": [
            {"symbol": symbol, "quantity": decimal_text(quantity)}
            for symbol, quantity in positions
            if quantity is not None
        ],
    }


def latest_reviews(db: Session, reconciliation_ids: list[str]) -> dict[str, dict]:
    """Latest admin review per reconciliation, read from the audit log.

    ``TradingReconciliation`` rows are immutable, so a review is an appended
    ``LIVE_RECONCILIATION_REVIEWED`` audit row keyed
    ``audit:recon-review:<reconciliation id>:<nonce>``.
    """
    if not reconciliation_ids:
        return {}
    rows = (
        db.query(TradingAuditLog)
        .filter(
            TradingAuditLog.action == RECONCILIATION_REVIEW_ACTION,
            or_(*[TradingAuditLog.idempotency_key.like(f"audit:recon-review:{rid}:%") for rid in reconciliation_ids]),
        )
        .order_by(TradingAuditLog.created_at.desc(), TradingAuditLog.id.desc())
        .all()
    )
    reviews: dict[str, dict] = {}
    for row in rows:
        rid = (row.request_json or {}).get("reconciliation_id")
        if not rid or rid in reviews:
            continue
        reviews[rid] = {
            "status": row.status,
            "note": (row.request_json or {}).get("note"),
            "reviewed_by": (row.request_json or {}).get("admin_user_id"),
            "reviewed_at": _iso(row.created_at),
        }
    return reviews


def serialize_reconciliation(row: TradingReconciliation, review: dict | None = None, *, include_reviewer: bool = False) -> dict:
    data = {
        "id": row.id,
        "account_id": row.account_id,
        "mandate_id": row.mandate_id,
        "status": row.status,
        "exchange_balance": _normalize_amounts(row.exchange_balance_json or {}),
        "ledger_balance": _normalize_amounts(row.ledger_balance_json or {}),
        "nav": _normalize_amounts(row.nav_json or {}),
        "differences": _normalize_amounts(row.differences_json or []),
        "actions": list(row.actions_json or []),
        "created_at": _iso(row.created_at),
        "reviewed": None,
    }
    if review:
        data["reviewed"] = {
            "status": review["status"],
            "reviewed_at": review["reviewed_at"],
            **({"note": review["note"], "reviewed_by": review["reviewed_by"]} if include_reviewer else {}),
        }
    return data


def reconciliation_view(
    db: Session,
    user_id: str,
    *,
    account_id: str | None = None,
    history: int = 10,
) -> dict:
    account = resolve_account(db, user_id, account_id)
    rows = (
        db.query(TradingReconciliation)
        .filter(
            TradingReconciliation.account_id == account.id,
            TradingReconciliation.user_id == user_id,
        )
        .order_by(TradingReconciliation.created_at.desc(), TradingReconciliation.id.desc())
        .limit(max(1, min(history, 50)))
        .all()
    )
    reviews = latest_reviews(db, [row.id for row in rows])
    return {
        "account": serialize_account(account),
        "ledger": ledger_summary(db, user_id, account.id),
        # ``None`` = this account was never reconciled: the comparison is
        # unavailable, which is not the same as "no differences".
        "latest": serialize_reconciliation(rows[0], reviews.get(rows[0].id)) if rows else None,
        "history": [
            {
                "id": row.id,
                "status": row.status,
                "created_at": _iso(row.created_at),
                "difference_count": len(row.differences_json or []),
                "reviewed": row.id in reviews,
            }
            for row in rows
        ],
    }
