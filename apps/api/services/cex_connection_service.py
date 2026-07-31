"""Private CEX (Binance/OKX/Bybit) read-only portfolio connections (P0-7).

Users connect venue-issued READ-ONLY API keys. The service:

1. Validates credentials against a signed read-only endpoint (permission
   check) BEFORE anything is persisted — invalid keys never create rows.
2. Persists credentials ONLY as Fernet ciphertext on
   ``ExchangeConnection.credential_ciphertext`` via
   ``portfolio_service.encrypt_token``. Plaintext keys never touch logs,
   metadata, or API responses.
3. Runs the first sync inline. On failure the connection stays with
   ``status=ERROR`` + ``error_message`` (set by ``sync_account``) and other
   accounts are unaffected.

Read-only venue access only: no order, trade, transfer, or withdrawal
endpoint is ever called.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.data.cex_private import CEX_VENUES, adapter_for, filter_dust
from packages.database.models import AccountSnapshot, TradingAccount, User

logger = logging.getLogger(__name__)

_EVM_PRIVATE_KEY_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

# Snapshot staleness is surfaced by portfolio_service._snapshot_is_stale for
# every non-Plaid venue; syncs older than this are flagged on the view layer.
CEX_SYNC_STALE_AFTER = timedelta(minutes=15)


def _assert_safe_key_material(api_key: str, api_secret: str, passphrase: str | None) -> None:
    """Reject wallet private keys / seed phrases pasted into CEX fields.

    Only exchange-issued API credentials are accepted here; an EVM private key
    or recovery phrase would grant FULL account control and must never be
    stored.
    """
    for value in (api_key, api_secret, passphrase or ""):
        candidate = value.strip()
        if not candidate:
            continue
        if _EVM_PRIVATE_KEY_RE.fullmatch(candidate):
            raise ValueError("CEX_KEY_MATERIAL_REJECTED: wallet private keys are not accepted; use exchange-issued read-only API credentials")
        words = [word for word in re.split(r"\s+", candidate) if word]
        if len(words) >= 12 and all(word.isalpha() for word in words):
            raise ValueError("CEX_KEY_MATERIAL_REJECTED: recovery/seed phrases are not accepted; use exchange-issued read-only API credentials")


def connect_cex(
    db: Session,
    user: User,
    venue: str,
    api_key: str,
    api_secret: str,
    passphrase: str | None = None,
    environment: str = "production",
) -> TradingAccount:
    """Permission-check, persist encrypted credentials, and run the first sync.

    Reconnecting the same venue UPDATES the existing account/connection
    (``portfolio_service._account`` dedupes per user+venue) instead of
    creating duplicates. A failed first sync leaves the connection in
    ``ERROR`` and does not raise — other accounts stay unaffected.
    """
    from apps.api.services.portfolio_service import _account, _connection, sync_account

    normalized = (venue or "").strip().lower()
    if normalized not in CEX_VENUES:
        raise ValueError(f"Unsupported CEX venue: {venue}")
    environment = (environment or "production").strip().lower()
    if environment not in {"production", "testnet"}:
        raise ValueError("environment must be production or testnet")
    api_key = (api_key or "").strip()
    api_secret = (api_secret or "").strip()
    passphrase = (passphrase or "").strip() or None
    if not api_key or not api_secret:
        raise ValueError("API key and secret are required")
    _assert_safe_key_material(api_key, api_secret, passphrase)

    settings = get_settings()
    adapter = adapter_for(
        normalized,
        environment=environment,
        timeout_seconds=settings.provider_http_timeout_seconds,
        max_response_bytes=settings.provider_max_response_bytes,
    )
    # Raises CexPermissionDenied on rejection; nothing is persisted in that case.
    check = adapter.validate_credentials(api_key, api_secret, passphrase)

    account = _account(
        db,
        user,
        normalized.upper(),
        f"{normalized.capitalize()} (read-only)",
        {"cex_environment": environment},
        json.dumps({"api_key": api_key, "api_secret": api_secret, "passphrase": passphrase}),
    )
    connection = _connection(db, account)
    connection.environment = environment
    connection.metadata_json = {
        **(connection.metadata_json or {}),
        "cex_environment": environment,
        "api_key_hint": f"...{api_key[-4:]}" if len(api_key) >= 4 else "****",
        "permission_check": {
            "can_trade": check.can_trade if check.permissions_verified else False,
            "can_withdraw": check.can_withdraw if check.permissions_verified else False,
            "permissions_verified": check.permissions_verified,
            **check.metadata,
        },
        "capability_notes": list(adapter.capability_notes),
    }
    db.commit()

    try:
        sync_account(db, user, account)
    except Exception:
        # sync_account already marked the connection ERROR with error_message.
        logger.warning("cex_first_sync_failed account_id=%s venue=%s", account.id, normalized)
    return account


def cex_connection_status(db: Session, account: TradingAccount) -> str | None:
    """DB-level connection status (used for the connect response contract).

    Distinct from the portfolio view's *effective* status, which may mark a
    fresh snapshot STALE based on age; the connect contract cares about the
    persisted connection state after the first sync.
    """
    from apps.api.services.portfolio_service import _connection

    return _connection(db, account).status


def sync_cex_account(db: Session, account: TradingAccount) -> None:
    """Fetch balances → normalize → persist one snapshot + position rows.

    Idempotent per run: every sync writes a NEW AccountSnapshot plus its
    PositionSnapshot rows (snapshot-per-run semantics shared with the other
    providers), so re-running never mutates or duplicates prior snapshots.
    """
    from apps.api.services.portfolio_service import _STABLECOIN_SYMBOLS, _connection, _save_snapshot, decrypt_token

    connection = _connection(db, account)
    credentials = json.loads(decrypt_token(connection.credential_ciphertext or ""))
    settings = get_settings()
    adapter = adapter_for(
        connection.adapter,
        environment=connection.environment or "production",
        timeout_seconds=settings.provider_http_timeout_seconds,
        max_response_bytes=settings.provider_max_response_bytes,
    )
    holdings = filter_dust(adapter.fetch_balances(credentials["api_key"], credentials["api_secret"], credentials.get("passphrase")))

    equity = 0.0
    available = 0.0
    priced_count = 0
    positions = []
    for holding in holdings:
        priced = holding.usd_value is not None
        value = float(holding.usd_value or 0.0)
        price = (value / holding.quantity) if priced and holding.quantity > 0 else 0.0
        if priced:
            priced_count += 1
            equity += value
            if holding.symbol in _STABLECOIN_SYMBOLS:
                available += value
        positions.append(
            {
                "symbol": holding.symbol,
                "quantity": holding.quantity,
                "price": price,
                "value": value,
                "cost": price,
                "meta": {
                    "name": holding.symbol,
                    "base_symbol": holding.symbol,
                    "asset_class": "stablecoin" if holding.symbol in _STABLECOIN_SYMBOLS else "crypto",
                    "priced": priced,
                    "venue": connection.adapter,
                    **holding.raw,
                },
            }
        )
    positions.sort(key=lambda item: item["value"], reverse=True)

    previous = (
        db.query(AccountSnapshot)
        .filter_by(user_id=account.user_id, account_id=account.id)
        .order_by(AccountSnapshot.captured_at.desc())
        .first()
    )
    daily_pnl = round(equity - float(previous.equity), 2) if previous else 0.0
    top1_weight = max((item["value"] / equity for item in positions), default=0.0) if equity > 0 else 0.0
    hhi = sum((item["value"] / equity) ** 2 for item in positions) if equity > 0 else 0.0
    raw = {
        "environment": connection.environment or "production",
        "holding_count": len(positions),
        "priced_holdings": priced_count,
        "unpriced_holdings": len(positions) - priced_count,
        "priced_coverage": round(priced_count / len(positions), 4) if positions else 1.0,
        "top1_weight": round(top1_weight, 6),
        "hhi": round(hhi, 6),
        "previous_nav": float(previous.equity) if previous else None,
        "capability_notes": list(adapter.capability_notes),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_snapshot(db, account, equity, available, raw, positions, connection.adapter, daily_pnl=daily_pnl)
