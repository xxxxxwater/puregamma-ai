from __future__ import annotations

import json
import logging
import math
import hashlib
import hmac
from datetime import date, datetime, timedelta, timezone

import jwt
import requests
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.services.entitlement_service import get_user_entitlement
from packages.database.models import AccountSnapshot, ExchangeConnection, PortfolioAutopilotReview, PortfolioInvestmentTransaction, PositionSnapshot, Report, TradingAccount, User, UserPreference, utcnow

logger = logging.getLogger(__name__)


class PortfolioAccessError(PermissionError):
    """Raised when a plan or subscription state blocks portfolio connections."""

    def __init__(self, code: str, context: dict):
        super().__init__(code)
        self.code = code
        self.context = context


class PlaidDataPending(RuntimeError):
    """Plaid has accepted a request but Investments data is not ready yet."""


class PlaidRefreshRateLimited(RuntimeError):
    """Protect against accidental repeated billable Investments Refresh calls."""


class PlaidRefreshUnsupported(RuntimeError):
    """The connected institution does not support Investments Refresh."""


class PlaidWebhookVerificationError(PermissionError):
    """Raised when a Plaid webhook cannot be authenticated."""

_MORALIS_CHAIN_BY_ID = {
    1: "eth",
    10: "optimism",
    56: "bsc",
    100: "gnosis",
    137: "polygon",
    250: "fantom",
    1284: "moonbeam",
    1285: "moonriver",
    8453: "base",
    42161: "arbitrum",
    43114: "avalanche",
    59144: "linea",
}
_MORALIS_TEST_CHAIN_MARKERS = ("testnet", "sepolia", "amoy", "moonbase")
# Mainnet catalog synced for every wallet. Moralis active-chain discovery only
# reports a subset of networks (verified against production API), so relying on
# it alone silently drops L2 assets from NAV.
_EVM_CHAIN_CATALOG = ("eth", "polygon", "bsc", "arbitrum", "optimism", "base", "avalanche", "linea", "fantom", "gnosis", "moonbeam", "moonriver")
_EVM_NATIVE_SYMBOL = {
    "eth": "ETH",
    "polygon": "POL",
    "bsc": "BNB",
    "arbitrum": "ETH",
    "optimism": "ETH",
    "base": "ETH",
    "avalanche": "AVAX",
    "linea": "ETH",
    "fantom": "FTM",
    "gnosis": "XDAI",
    "moonbeam": "GLMR",
    "moonriver": "MOVR",
}
# Wrapped native token contracts used to price the native asset when the
# aggregated wallet token endpoint is unavailable for a chain.
_EVM_WRAPPED_NATIVE = {
    "eth": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    "polygon": "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270",
    "bsc": "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
    "arbitrum": "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
    "optimism": "0x4200000000000000000000000000000000000006",
    "base": "0x4200000000000000000000000000000000000006",
    "avalanche": "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7",
    "linea": "0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f",
    "fantom": "0x21be370d5312f44cb42ce377bc9b8a0cef1a4c83",
    "gnosis": "0xe91d153e0b41518a2ce8dd3d7944fa863463a97d",
    "moonbeam": "0xacc15dc74880c9944775448304b263d191c6077f",
    "moonriver": "0x98878b06940ae243284ca214f92bb71a2b032b8a",
}
_STABLECOIN_SYMBOLS = {"USDC", "USDT", "DAI", "USDE", "USDH", "PYUSD", "FRAX", "LUSD", "USDD", "GUSD", "TUSD", "USDP", "XDAI", "USDC.E", "USDBC", "EURC"}
_EQUITY_PROXY_SYMBOLS = {"MSTR", "IBIT", "STRC", "STRD", "STRK", "STRF"}
_EVM_MAX_STORED_POSITIONS = 300
_EVM_MIN_POSITION_VALUE = 0.01


def _finite(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _fernet() -> Fernet:
    key = get_settings().portfolio_token_encryption_key
    if not key:
        raise RuntimeError("PORTFOLIO_TOKEN_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise RuntimeError("PORTFOLIO_TOKEN_ENCRYPTION_KEY must be a Fernet key") from exc


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Stored portfolio credential cannot be decrypted") from exc


def _account(db: Session, user: User, venue: str, name: str, metadata: dict, token: str | None = None) -> TradingAccount:
    account = None
    identity = metadata.get("item_id") or metadata.get("wallet_address") or venue
    candidates = db.query(TradingAccount).filter_by(user_id=user.id, venue=venue, account_type="READ_ONLY").all()
    for candidate in candidates:
        existing = db.query(ExchangeConnection).filter_by(user_id=user.id, account_id=candidate.id, adapter=venue.lower()).one_or_none()
        existing_identity = ((existing.metadata_json or {}).get("item_id") or (existing.metadata_json or {}).get("wallet_address") or venue) if existing else None
        if existing_identity == identity:
            account = candidate
            break
    if not account:
        entitlement = get_user_entitlement(db, user.id)
        account_count = db.query(TradingAccount).filter_by(user_id=user.id, account_type="READ_ONLY", status="ACTIVE").count()
        context = {
            "plan": entitlement["effective_plan"],
            "active_count": account_count,
            "max_portfolios": entitlement["max_portfolios"],
        }
        if entitlement["portfolio_access"] != "standard":
            raise PortfolioAccessError("PORTFOLIO_ACCESS_RESTRICTED", {**context, "reason": entitlement.get("restricted_reason") or "subscription_restricted"})
        if account_count >= entitlement["max_portfolios"]:
            raise PortfolioAccessError("PORTFOLIO_LIMIT_REACHED", context)
        account = TradingAccount(user_id=user.id, name=name, venue=venue, account_type="READ_ONLY", base_currency="USD", status="ACTIVE", permissions_json={"read_positions": True, "trade": False, "withdraw": False, "transfer": False})
        db.add(account)
        db.flush()
    connection = db.query(ExchangeConnection).filter_by(user_id=user.id, account_id=account.id, adapter=venue.lower()).one_or_none()
    if not connection:
        connection = ExchangeConnection(user_id=user.id, account_id=account.id, adapter=venue.lower(), environment="production", status="CONNECTED")
        db.add(connection)
    connection.status = "CONNECTED"
    connection.metadata_json = metadata
    if token:
        connection.credential_ciphertext = encrypt_token(token)
    connection.last_health_at = utcnow()
    account.status = "ACTIVE"
    db.commit()
    db.refresh(account)
    return account


def _connection(db: Session, account: TradingAccount) -> ExchangeConnection:
    row = db.query(ExchangeConnection).filter_by(account_id=account.id, user_id=account.user_id).one()
    return row


def _snapshot_is_stale(account: TradingAccount, snapshot: AccountSnapshot) -> bool:
    limit = timedelta(hours=36) if account.venue == "PLAID" else timedelta(minutes=15)
    return bool(snapshot.stale or datetime.now(timezone.utc) - snapshot.captured_at.astimezone(timezone.utc) > limit)


def _plaid_base_url() -> str:
    environment = get_settings().plaid_env.strip().lower()
    if environment not in {"sandbox", "production"}:
        raise RuntimeError("PLAID_ENV must be sandbox or production")
    return f"https://{environment}.plaid.com"


def _plaid_request(path: str, access_token: str | None = None, *, payload: dict | None = None, timeout: int = 45) -> requests.Response:
    settings = get_settings()
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise RuntimeError("Plaid Investments is not configured")
    body = {"client_id": settings.plaid_client_id, "secret": settings.plaid_secret, **(payload or {})}
    if access_token:
        body["access_token"] = access_token
    return requests.post(f"{_plaid_base_url()}{path}", json=body, timeout=timeout)


def _plaid_error_code(response: requests.Response) -> str | None:
    try:
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return str(payload.get("error_code") or "") or None


def _parse_aware_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _plaid_webhook_url() -> str:
    return str(getattr(get_settings(), "plaid_webhook_url", "") or "").strip()


def _update_plaid_webhook(connection: ExchangeConnection, token: str) -> None:
    """Register the receiver for existing Items without blocking portfolio sync.

    Link only applies its webhook field when an Item is created. Updating here
    also upgrades Items linked before webhook support was added.
    """
    webhook_url = _plaid_webhook_url()
    if not webhook_url:
        return
    metadata = dict(connection.metadata_json or {})
    if metadata.get("plaid_webhook_url") == webhook_url:
        return
    try:
        response = _plaid_request("/item/webhook/update", token, payload={"webhook": webhook_url}, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("plaid_webhook_update_failed account_id=%s error=%s", connection.account_id, type(exc).__name__)
        metadata["plaid_webhook_error"] = type(exc).__name__
    else:
        metadata["plaid_webhook_url"] = webhook_url
        metadata.pop("plaid_webhook_error", None)
    connection.metadata_json = metadata


def plaid_link_token(user: User) -> str:
    settings = get_settings()
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise RuntimeError("Plaid Investments is not configured")
    environment = settings.plaid_env.strip().lower()
    _plaid_base_url()
    if environment == "production" and not settings.plaid_redirect_uri.startswith("https://"):
        raise RuntimeError("Plaid Production requires an HTTPS redirect URI")
    payload = {
        "client_name": "PureGamma AI",
        "language": "en",
        "country_codes": ["US", "CA"],
        "user": {"client_user_id": user.id},
        "products": ["investments"],
        "redirect_uri": settings.plaid_redirect_uri,
    }
    if bool(getattr(settings, "plaid_cash_transactions_enabled", False)):
        # Keep brokerage-only institutions selectable while asking Plaid to
        # prepare the user-authorized cash-account history when available.
        payload["optional_products"] = ["transactions"]
        payload["transactions"] = {"days_requested": 730}
    if _plaid_webhook_url():
        payload["webhook"] = _plaid_webhook_url()
    response = _plaid_request("/link/token/create", payload=payload, timeout=25)
    response.raise_for_status()
    return response.json()["link_token"]


def connect_plaid(db: Session, user: User, public_token: str, institution_name: str = "Plaid Investments") -> TradingAccount:
    _plaid_base_url()
    response = _plaid_request("/item/public_token/exchange", payload={"public_token": public_token}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    account = _account(
        db,
        user,
        "PLAID",
        institution_name,
        {
            "item_id": payload.get("item_id"),
            "institution_name": institution_name,
            # Never activate a newly billable product on legacy Items merely
            # because the application was upgraded. Only Link sessions created
            # with the explicit optional Transactions consent receive this.
            "plaid_cash_transactions_requested": bool(
                getattr(get_settings(), "plaid_cash_transactions_enabled", False)
            ),
        },
        payload["access_token"],
    )
    _update_plaid_webhook(_connection(db, account), payload["access_token"])
    db.commit()
    return account


def connect_hyperliquid(db: Session, user: User, address: str) -> TradingAccount:
    normalized = address.strip().lower()
    if not normalized.startswith("0x") or len(normalized) != 42 or any(ch not in "0123456789abcdef" for ch in normalized[2:]):
        raise ValueError("Invalid Hyperliquid wallet address")
    return _account(db, user, "HYPERLIQUID", "Hyperliquid", {"wallet_address": normalized})


def connect_evm_wallet(db: Session, user: User, address: str, chain_id: int) -> TradingAccount:
    settings = get_settings()
    if not settings.moralis_api_key:
        raise RuntimeError("MORALIS_API_KEY is required for multi-chain EVM portfolio sync")
    normalized = address.strip().lower()
    if not normalized.startswith("0x") or len(normalized) != 42 or any(ch not in "0123456789abcdef" for ch in normalized[2:]):
        raise ValueError("Invalid EVM wallet address")
    return _account(
        db,
        user,
        "EVM",
        f"MetaMask {normalized[:6]}...{normalized[-4:]}",
        {"wallet_address": normalized, "verified_chain_id": chain_id, "verification": "EIP-4361"},
    )


def connect_ibkr_token(db: Session, user: User, token_payload: dict) -> TradingAccount:
    metadata = {"expires_at": int(datetime.now(timezone.utc).timestamp()) + int(token_payload.get("expires_in") or 3600)}
    return _account(db, user, "IBKR", "Interactive Brokers", metadata, json.dumps(token_payload))


def _maybe_create_first_portfolio_brief(db: Session, user: User, account: TradingAccount) -> None:
    """Create the user's first deterministic portfolio brief after a sync.

    Fires once per (user, account) for ANY provider: the render is the
    non-LLM ``portfolio_daily`` renderer, so onboarding personalization never
    consumes LLM credits. Idempotent via
    ``first-portfolio-brief:{user}:{account}`` and never allowed to break the
    sync itself (isolated in a SAVEPOINT).
    """
    try:
        from apps.api.services.daily_report_renderers import render_daily_report

        idempotency_key = f"first-portfolio-brief:{user.id}:{account.id}"
        with db.begin_nested():
            if db.query(Report).filter_by(idempotency_key=idempotency_key).one_or_none():
                return
            preference = db.query(UserPreference).filter_by(user_id=user.id).one_or_none()
            language = "zh" if (preference and preference.locale == "zh") else "en"
            today = datetime.now(timezone.utc).date()
            rendered = render_daily_report(db, user.id, "portfolio_daily", language, today)
            db.add(
                Report(
                    user_id=user.id,
                    title=rendered["title"],
                    report_type="portfolio_daily",
                    language=language,
                    content_markdown=rendered["content_markdown"],
                    assets=rendered.get("assets") or [],
                    source_intelligence_id=rendered.get("source_intelligence_id"),
                    report_date=today,
                    status="completed",
                    idempotency_key=idempotency_key,
                )
            )
    except Exception:
        logger.exception("first_portfolio_brief_failed user_id=%s account_id=%s", user.id, account.id)


def sync_account(db: Session, user: User, account: TradingAccount, *, include_transactions: bool = True) -> None:
    if account.user_id != user.id:
        raise LookupError("Account not found")
    try:
        if account.venue == "HYPERLIQUID":
            _sync_hyperliquid(db, account)
        elif account.venue == "EVM":
            _sync_evm(db, account)
        elif account.venue == "PLAID":
            _sync_plaid(db, account, include_transactions=include_transactions)
        elif account.venue == "IBKR":
            _sync_ibkr(db, account)
        elif account.venue in {"BINANCE", "OKX", "BYBIT"}:
            # Lazy import: cex_connection_service depends on this module.
            from apps.api.services.cex_connection_service import sync_cex_account

            sync_cex_account(db, account)
        else:
            raise ValueError("Unsupported portfolio provider")
        from packages.billing.rewards import grant_reward

        grant_reward(
            db,
            user.id,
            "onboarding_portfolio_grant",
            200,
            idempotency_key=f"portfolio-onboarding:{user.id}",
            source="first_successful_portfolio_sync",
            metadata={"account_id": account.id, "provider": account.venue},
        )
        _maybe_create_first_portfolio_brief(db, user, account)
        db.commit()
    except PlaidDataPending:
        db.rollback()
        connection = _connection(db, account)
        connection.status = "PENDING_HISTORY"
        connection.error_code = "PLAID_PRODUCT_NOT_READY"
        connection.error_message = "Plaid is still preparing investment transaction history"
        db.commit()
        raise
    except Exception as exc:
        db.rollback()
        connection = _connection(db, account)
        connection.status = "ERROR"
        connection.error_code = "SYNC_FAILED"
        connection.error_message = str(exc)[:500]
        db.commit()
        raise


def _sync_hyperliquid(db: Session, account: TradingAccount) -> None:
    settings = get_settings()
    connection = _connection(db, account)
    address = connection.metadata_json["wallet_address"]
    response = requests.post(f"{settings.hyperliquid_api_url.rstrip('/')}/info", json={"type": "clearinghouseState", "user": address}, timeout=15)
    response.raise_for_status()
    data = response.json()
    summary = data.get("marginSummary", {})
    equity = float(summary.get("accountValue") or 0)
    margin = float(summary.get("totalMarginUsed") or 0)
    spot_response = requests.post(f"{settings.hyperliquid_api_url.rstrip('/')}/info", json={"type": "spotClearinghouseState", "user": address}, timeout=15)
    mids_response = requests.post(f"{settings.hyperliquid_api_url.rstrip('/')}/info", json={"type": "allMids"}, timeout=15)
    spot_response.raise_for_status()
    mids_response.raise_for_status()
    spot_data = spot_response.json()
    mids = mids_response.json()
    spot_positions = []
    spot_value = 0.0
    for balance in spot_data.get("balances", []):
        coin = str(balance.get("coin") or "UNKNOWN")
        quantity = float(balance.get("total") or 0)
        price = 1.0 if coin in {"USDC", "USDT", "USDH"} else float(mids.get(coin) or 0)
        value = quantity * price
        spot_value += value
        spot_positions.append({"symbol": coin, "quantity": quantity, "price": price, "value": value, "cost": float(balance.get("entryNtl") or 0)})
    equity += spot_value
    raw = {"perpetual": data, "spot": spot_data}
    _save_snapshot(db, account, equity, max(equity - margin, 0), raw, [*data.get("assetPositions", []), *spot_positions], "hyperliquid")


def _evm_native_fallback(address: str, chain: str, base_url: str, headers: dict) -> dict | None:
    """Read the native asset directly when the aggregated token endpoint fails.

    Moralis rejects wallets with very large token sets on /wallets/{address}/tokens
    (HTTP 400 "too many ERC20 token balances"). The plain balance endpoint keeps
    working, so we still surface the native holding instead of an empty chain.
    """
    try:
        balance_response = requests.get(f"{base_url}/{address}/balance", params={"chain": chain}, headers=headers, timeout=30)
        balance_response.raise_for_status()
        wei = _finite((balance_response.json() or {}).get("balance"))
    except Exception as exc:
        logger.warning("moralis_native_balance_failed address=%s chain=%s error=%s", address, chain, exc)
        return None
    quantity = wei / 1e18
    if not math.isfinite(quantity) or quantity <= 0:
        return None
    price = 0.0
    change_pct = 0.0
    wrapped = _EVM_WRAPPED_NATIVE.get(chain)
    if wrapped:
        try:
            price_response = requests.get(f"{base_url}/erc20/{wrapped}/price", params={"chain": chain, "include": "percent_change"}, headers=headers, timeout=30)
            price_response.raise_for_status()
            payload = price_response.json() or {}
            price = _finite(payload.get("usdPrice"))
            change_pct = _finite(payload.get("24hrPercentChange"))
        except Exception as exc:
            logger.warning("moralis_native_price_failed address=%s chain=%s error=%s", address, chain, exc)
    symbol = _EVM_NATIVE_SYMBOL.get(chain, chain.upper())
    value = quantity * price
    return {
        "symbol": symbol,
        "name": symbol,
        "token_address": None,
        "balance_formatted": str(quantity),
        "usd_price": price,
        "usd_value": value,
        "usd_value_24hr_usd_change": value * change_pct / 100 if change_pct else 0.0,
        "usd_price_24hr_percent_change": change_pct,
        "possible_spam": False,
        "verified_contract": True,
        "native_token": True,
        "logo": None,
        "_chain": chain,
        "_fallback": True,
    }


def _sync_evm(db: Session, account: TradingAccount) -> None:
    settings = get_settings()
    if not settings.moralis_api_key:
        raise RuntimeError("MORALIS_API_KEY is required for multi-chain EVM portfolio sync")
    connection = _connection(db, account)
    address = str((connection.metadata_json or {}).get("wallet_address") or "")
    base_url = settings.moralis_api_url.rstrip("/")
    headers = {
        "X-API-Key": settings.moralis_api_key,
        "Accept": "application/json",
    }
    chains: list[str] = []
    chain_ids: dict[str, str] = {}
    try:
        active_response = requests.get(
            f"{base_url}/wallets/{address}/chains",
            headers=headers,
            timeout=45,
        )
        active_response.raise_for_status()
        active_payload = active_response.json()
        for item in active_payload.get("active_chains", []):
            chain = str(item.get("chain") or "").strip().lower()
            if not chain or any(marker in chain for marker in _MORALIS_TEST_CHAIN_MARKERS):
                continue
            if chain not in chains:
                chains.append(chain)
                chain_ids[chain] = str(item.get("chain_id") or chain)
    except Exception as exc:
        logger.warning("moralis_active_chains_failed address=%s error=%s", address, exc)
    for chain in _EVM_CHAIN_CATALOG:
        if chain not in chains:
            chains.append(chain)
    connected_chain_id = int((connection.metadata_json or {}).get("verified_chain_id") or (connection.metadata_json or {}).get("chain_id") or 1)
    fallback_chain = _MORALIS_CHAIN_BY_ID.get(connected_chain_id, "eth")
    if fallback_chain not in chains:
        chains.append(fallback_chain)
    chain_ids.setdefault(fallback_chain, str(connected_chain_id))

    assets = []
    chain_errors = []
    chains_with_data = []
    for chain in chains:
        cursor = None
        chain_failed = False
        chain_assets = 0
        for _page in range(10):
            params = {"chain": chain, "limit": 100, "exclude_spam": "true"}
            if cursor:
                params["cursor"] = cursor
            try:
                response = requests.get(
                    f"{base_url}/wallets/{address}/tokens",
                    params=params,
                    headers=headers,
                    timeout=45,
                )
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                chain_failed = True
                chain_errors.append({"chain": chain, "error": str(exc)[:160]})
                logger.warning(
                    "moralis_wallet_tokens_failed address=%s chain=%s error=%s",
                    address,
                    chain,
                    exc,
                )
                break
            for asset in payload.get("result", []):
                assets.append({**asset, "_chain": chain})
                chain_assets += 1
            cursor = payload.get("cursor")
            if not cursor:
                break
        if chain_failed:
            fallback_asset = _evm_native_fallback(address, chain, base_url, headers)
            if fallback_asset:
                assets.append(fallback_asset)
                chain_assets += 1
                chain_errors[-1]["fallback"] = "native_balance"
        if chain_assets:
            chains_with_data.append(chain)
    if chain_errors and len(chain_errors) == len(chains) and not assets:
        raise RuntimeError("Moralis could not read token balances on active EVM chains")

    positions = []
    equity = 0.0
    available = 0.0
    daily_pnl = 0.0
    unpriced_count = 0
    for asset in assets:
        if asset.get("possible_spam") is True:
            continue
        value = _finite(asset.get("usd_value"))
        quantity = _finite(asset.get("balance_formatted"))
        price = _finite(asset.get("usd_price"))
        if value <= 0 and quantity <= 0:
            continue
        symbol = str(asset.get("symbol") or asset.get("name") or "UNKNOWN")
        chain = str(asset.get("_chain") or "unknown")
        change_24h = _finite(asset.get("usd_value_24hr_usd_change"))
        change_24h_pct = _finite(asset.get("usd_price_24hr_percent_change"))
        priced = value > 0 and price > 0
        equity += max(value, 0)
        if priced:
            daily_pnl += change_24h
        else:
            unpriced_count += 1
        if symbol.upper() in _STABLECOIN_SYMBOLS:
            available += max(value, 0)
        positions.append(
            {
                "symbol": f"{symbol} @ {chain}",
                "quantity": quantity,
                "price": price,
                "value": value,
                "cost": price,
                "meta": {
                    "base_symbol": symbol,
                    "name": str(asset.get("name") or symbol),
                    "chain": chain,
                    "token_address": asset.get("token_address"),
                    "native": bool(asset.get("native_token")),
                    "verified": bool(asset.get("verified_contract")),
                    "priced": priced,
                    "fallback": bool(asset.get("_fallback")),
                    "logo": asset.get("logo") or asset.get("thumbnail"),
                    "change_24h": change_24h,
                    "change_24h_pct": change_24h_pct,
                },
            }
        )
    # Wallets can carry thousands of dust/spam tokens. Persist only material
    # holdings so repeated syncs do not bloat position_snapshots.
    priced_positions = [item for item in positions if item["value"] >= _EVM_MIN_POSITION_VALUE]
    priced_positions.sort(key=lambda item: item["value"], reverse=True)
    stored_positions = priced_positions[:_EVM_MAX_STORED_POSITIONS]
    raw = {
        "address": address,
        "asset_count": len(positions),
        "stored_asset_count": len(stored_positions),
        "unpriced_asset_count": unpriced_count,
        "chains": [
            {"chain": chain, "chain_id": chain_ids.get(chain, chain)}
            for chain in chains_with_data or chains
        ],
        "chain_errors": chain_errors,
    }
    _save_snapshot(db, account, equity, available, raw, stored_positions, "evm", daily_pnl=daily_pnl)


def _plaid_asset_class(security: dict) -> str:
    kind = str(security.get("type") or "").lower()
    if kind == "cryptocurrency":
        return "crypto"
    if kind == "cash" or security.get("is_cash_equivalent"):
        return "cash"
    return "equity"


def _sync_plaid_investment_transactions(
    db: Session,
    account: TradingAccount,
    token: str,
    securities: dict[str, dict],
) -> int:
    """Upsert the user-authorized 24-month Investments transaction window.

    Plaid returns stable reverse-chronological pages. After the first full import
    we re-read a short overlap window so corrected/cancelled transactions are
    reconciled without repeatedly billing the application for the whole history.
    """
    latest = (
        db.query(PortfolioInvestmentTransaction)
        .filter_by(account_id=account.id, provider="plaid")
        .filter(PortfolioInvestmentTransaction.external_id.like("investment:%"))
        .order_by(PortfolioInvestmentTransaction.posted_date.desc())
        .first()
    )
    today = datetime.now(timezone.utc).date()
    earliest = today - timedelta(days=730)
    start = earliest if not latest else max(earliest, latest.posted_date - timedelta(days=35))
    offset = 0
    total = None
    imported = 0
    while total is None or offset < total:
        response = _plaid_request(
            "/investments/transactions/get",
            token,
            payload={
                "start_date": start.isoformat(),
                "end_date": today.isoformat(),
                "options": {"count": 500, "offset": offset},
            },
            timeout=150,
        )
        if response.status_code >= 400 and _plaid_error_code(response) == "PRODUCT_NOT_READY":
            raise PlaidDataPending("Plaid is still preparing investment transaction history")
        response.raise_for_status()
        payload = response.json()
        transaction_rows = list(payload.get("investment_transactions") or [])
        total = int(payload.get("total_investment_transactions") or len(transaction_rows))
        for security in payload.get("securities") or []:
            if security.get("security_id"):
                securities[str(security["security_id"])] = security
        for item in transaction_rows:
            transaction_id = str(item.get("investment_transaction_id") or "")
            posted_raw = str(item.get("date") or "")
            if not transaction_id or not posted_raw:
                continue
            external_id = f"investment:{transaction_id}"
            try:
                posted_date = date.fromisoformat(posted_raw)
            except ValueError:
                continue
            security = securities.get(str(item.get("security_id") or ""), {})
            values = {
                "user_id": account.user_id,
                "provider_account_id": str(item.get("account_id") or ""),
                "security_id": str(item.get("security_id") or "") or None,
                "posted_date": posted_date,
                "transaction_datetime": _parse_aware_datetime(item.get("transaction_datetime")),
                "name": str(item.get("name") or security.get("name") or "Investment activity"),
                "symbol": str(security.get("ticker_symbol") or security.get("name") or "") or None,
                "transaction_type": str(item.get("type") or "cash"),
                "subtype": str(item.get("subtype") or "") or None,
                "quantity": _finite(item.get("quantity")),
                "price": _finite(item.get("price")),
                "amount": _finite(item.get("amount")),
                "fees": _finite(item.get("fees")),
                "currency": item.get("iso_currency_code") or item.get("unofficial_currency_code"),
                "cancelled": str(item.get("type") or "").lower() == "cancel",
                "raw_event_reference": {
                    "security_type": security.get("type"),
                    "security_subtype": security.get("subtype"),
                    "is_cash_equivalent": bool(security.get("is_cash_equivalent")),
                },
            }
            row = (
                db.query(PortfolioInvestmentTransaction)
                .filter_by(account_id=account.id, provider="plaid", external_id=external_id)
                .one_or_none()
            )
            if row:
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                db.add(
                    PortfolioInvestmentTransaction(
                        account_id=account.id,
                        provider="plaid",
                        external_id=external_id,
                        **values,
                    )
                )
            imported += 1
        offset += len(transaction_rows)
        if not transaction_rows:
            break
    db.commit()
    return imported


def _sync_plaid_cash_transactions(db: Session, account: TradingAccount, token: str) -> int:
    """Apply incremental Plaid Transactions updates for non-investment accounts.

    The cursor lives with the encrypted Item connection, never in a client
    request. This follows Plaid's pagination rule: if the update mutates during
    pagination, restart from the cursor that began the update batch.
    """
    connection = _connection(db, account)
    metadata = dict(connection.metadata_json or {})
    initial_cursor = metadata.get("plaid_transactions_cursor")
    cursor = str(initial_cursor) if initial_cursor else None
    restart_count = 0

    while True:
        added: list[dict] = []
        modified: list[dict] = []
        removed: list[dict] = []
        cursor_for_page = cursor
        next_cursor = cursor
        update_status = None
        try:
            while True:
                response = _plaid_request(
                    "/transactions/sync",
                    token,
                    payload={"cursor": cursor_for_page, "count": 500},
                    timeout=90,
                )
                error_code = _plaid_error_code(response)
                if response.status_code >= 400 and error_code == "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION":
                    if restart_count >= 1:
                        response.raise_for_status()
                    restart_count += 1
                    raise RuntimeError("restart_transactions_sync")
                # Transactions is optional for an investment Item. Do not make
                # its absence block core NAV or investment activity retrieval.
                if response.status_code >= 400 and error_code in {
                    "PRODUCT_NOT_READY",
                    "PRODUCT_NOT_SUPPORTED",
                    "PRODUCT_NOT_ENABLED",
                    "INVALID_PRODUCT",
                }:
                    metadata["plaid_cash_transactions_status"] = error_code.lower()
                    connection.metadata_json = metadata
                    db.commit()
                    return 0
                response.raise_for_status()
                payload = response.json()
                added.extend(item for item in payload.get("added") or [] if isinstance(item, dict))
                modified.extend(item for item in payload.get("modified") or [] if isinstance(item, dict))
                removed.extend(item for item in payload.get("removed") or [] if isinstance(item, dict))
                next_cursor = payload.get("next_cursor") or next_cursor
                update_status = payload.get("transactions_update_status") or update_status
                if not payload.get("has_more"):
                    break
                cursor_for_page = next_cursor
        except RuntimeError as exc:
            if str(exc) != "restart_transactions_sync":
                raise
            cursor = str(initial_cursor) if initial_cursor else None
            continue

        changes = 0
        for item in [*added, *modified]:
            transaction_id = str(item.get("transaction_id") or "")
            posted_raw = str(item.get("date") or "")
            if not transaction_id or not posted_raw:
                continue
            try:
                posted_date = date.fromisoformat(posted_raw)
            except ValueError:
                continue
            category = item.get("personal_finance_category") or {}
            if not isinstance(category, dict):
                category = {}
            external_id = f"cash:{transaction_id}"
            values = {
                "user_id": account.user_id,
                "provider_account_id": str(item.get("account_id") or ""),
                "security_id": None,
                "posted_date": posted_date,
                "transaction_datetime": _parse_aware_datetime(item.get("datetime")),
                "name": str(item.get("merchant_name") or item.get("name") or "Cash activity"),
                "symbol": None,
                "transaction_type": "cash",
                "subtype": str(category.get("primary") or item.get("payment_channel") or "cash"),
                "quantity": 0.0,
                "price": 0.0,
                "amount": _finite(item.get("amount")),
                "fees": 0.0,
                "currency": item.get("iso_currency_code") or item.get("unofficial_currency_code"),
                "cancelled": False,
                "raw_event_reference": {
                    "source": "transactions",
                    "pending": bool(item.get("pending")),
                    "category_primary": category.get("primary"),
                    "category_detailed": category.get("detailed"),
                },
            }
            row = (
                db.query(PortfolioInvestmentTransaction)
                .filter_by(account_id=account.id, provider="plaid", external_id=external_id)
                .one_or_none()
            )
            if row:
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                db.add(
                    PortfolioInvestmentTransaction(
                        account_id=account.id,
                        provider="plaid",
                        external_id=external_id,
                        **values,
                    )
                )
            changes += 1
        for item in removed:
            transaction_id = str(item.get("transaction_id") or "")
            if transaction_id:
                db.query(PortfolioInvestmentTransaction).filter_by(
                    account_id=account.id,
                    provider="plaid",
                    external_id=f"cash:{transaction_id}",
                ).delete(synchronize_session=False)

        metadata["plaid_transactions_cursor"] = next_cursor
        metadata["plaid_cash_transactions_status"] = str(update_status or "unknown").lower()
        connection.metadata_json = metadata
        db.commit()
        return changes


def _sync_plaid(db: Session, account: TradingAccount, *, include_transactions: bool = True) -> None:
    connection = _connection(db, account)
    token = decrypt_token(connection.credential_ciphertext or "")
    _update_plaid_webhook(connection, token)
    response = _plaid_request("/investments/holdings/get", token, timeout=45)
    response.raise_for_status()
    data = response.json()
    securities = {str(item["security_id"]): item for item in data.get("securities", []) if item.get("security_id")}
    positions = []
    holdings_value_by_account: dict[str, float] = {}
    cash_value_by_account: dict[str, float] = {}
    daily_pnl = 0.0
    for holding in data.get("holdings", []):
        security = securities.get(str(holding.get("security_id") or ""), {})
        provider_account_id = str(holding.get("account_id") or "")
        quantity = _finite(holding.get("quantity"))
        price = _finite(holding.get("institution_price"))
        value = _finite(holding.get("institution_value"))
        prior_close = _finite(security.get("close_price"))
        if value <= 0 and quantity and price:
            value = quantity * price
        holdings_value_by_account[provider_account_id] = holdings_value_by_account.get(provider_account_id, 0.0) + max(value, 0.0)
        if _plaid_asset_class(security) == "cash":
            cash_value_by_account[provider_account_id] = cash_value_by_account.get(provider_account_id, 0.0) + max(value, 0.0)
        change = quantity * (price - prior_close) if quantity and price > 0 and prior_close > 0 else 0.0
        daily_pnl += change
        symbol = str(security.get("ticker_symbol") or security.get("name") or "UNKNOWN")
        positions.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "price": price,
                "value": value,
                "cost": _finite(holding.get("cost_basis")),
                "meta": {
                    "name": security.get("name") or symbol,
                    "provider_account_id": provider_account_id,
                    "security_id": holding.get("security_id"),
                    "asset_class": _plaid_asset_class(security),
                    "security_type": security.get("type"),
                    "security_subtype": security.get("subtype"),
                    "priced": price > 0 and value >= 0,
                    "cost_basis": _finite(holding.get("cost_basis")),
                    "change_24h": change,
                    "change_24h_pct": ((price - prior_close) / prior_close * 100) if prior_close > 0 else 0.0,
                },
            }
        )
    equity = 0.0
    available = 0.0
    account_summaries = []
    for item in data.get("accounts", []):
        provider_account_id = str(item.get("account_id") or "")
        balances = item.get("balances") or {}
        current = balances.get("current")
        current_value = _finite(current) if current is not None else holdings_value_by_account.get(provider_account_id, 0.0)
        account_equity = max(current_value, holdings_value_by_account.get(provider_account_id, 0.0))
        available_value = balances.get("available")
        account_available = _finite(available_value) if available_value is not None else cash_value_by_account.get(provider_account_id, 0.0)
        equity += account_equity
        available += account_available
        account_summaries.append(
            {
                "account_id": provider_account_id,
                "name": item.get("name"),
                "subtype": item.get("subtype"),
                "current": current_value,
                "available": account_available,
                "margin_loan_amount": _finite(balances.get("margin_loan_amount")),
            }
        )
    _save_snapshot(
        db,
        account,
        equity,
        available,
        {
            "request_id": data.get("request_id"),
            "item_id": (connection.metadata_json or {}).get("item_id"),
            "accounts": account_summaries,
            "holding_count": len(positions),
        },
        positions,
        "plaid",
        daily_pnl=daily_pnl,
    )
    if include_transactions:
        _sync_plaid_investment_transactions(db, account, token, securities)
        if bool((connection.metadata_json or {}).get("plaid_cash_transactions_requested")):
            _sync_plaid_cash_transactions(db, account, token)


def request_plaid_investments_refresh(db: Session, user: User, account: TradingAccount) -> dict:
    """Request a billable on-demand extraction without exposing Item credentials."""
    if account.user_id != user.id or account.venue != "PLAID" or account.account_type != "READ_ONLY":
        raise LookupError("Plaid portfolio account not found")
    connection = _connection(db, account)
    metadata = dict(connection.metadata_json or {})
    last_requested = _parse_aware_datetime(metadata.get("plaid_refresh_requested_at"))
    minimum_minutes = max(1, int(getattr(get_settings(), "plaid_investments_refresh_min_minutes", 15) or 15))
    if last_requested and datetime.now(timezone.utc) - last_requested < timedelta(minutes=minimum_minutes):
        raise PlaidRefreshRateLimited(
            f"Plaid Investments Refresh can be requested once every {minimum_minutes} minutes for this account"
        )
    token = decrypt_token(connection.credential_ciphertext or "")
    response = _plaid_request("/investments/refresh", token, timeout=55)
    if response.status_code >= 400 and _plaid_error_code(response) == "PRODUCT_NOT_SUPPORTED":
        metadata["plaid_refresh_supported"] = False
        connection.metadata_json = metadata
        db.commit()
        raise PlaidRefreshUnsupported("This institution does not support Plaid Investments Refresh")
    response.raise_for_status()
    payload = response.json()
    metadata.update(
        {
            "plaid_refresh_requested_at": utcnow().isoformat(),
            "plaid_refresh_request_id": payload.get("request_id"),
            "plaid_refresh_supported": True,
        }
    )
    connection.metadata_json = metadata
    connection.status = "PENDING_REFRESH"
    connection.error_code = None
    connection.error_message = None
    db.commit()
    return {
        "account_id": account.id,
        "status": "refresh_requested",
        "request_id": payload.get("request_id"),
        "retry_after_seconds": minimum_minutes * 60,
    }


def portfolio_account_for_plaid_item(db: Session, item_id: str) -> TradingAccount | None:
    """Resolve an Item only through the server-side connection catalog."""
    for connection in db.query(ExchangeConnection).filter_by(adapter="plaid").all():
        if str((connection.metadata_json or {}).get("item_id") or "") != item_id:
            continue
        account = db.get(TradingAccount, connection.account_id)
        if account and account.venue == "PLAID" and account.status == "ACTIVE":
            return account
    return None


def verify_plaid_webhook(raw_body: bytes, signed_jwt: str | None) -> None:
    """Verify Plaid's ES256 signature, body hash, and five-minute replay window."""
    if not signed_jwt:
        raise PlaidWebhookVerificationError("Missing Plaid-Verification header")
    try:
        header = jwt.get_unverified_header(signed_jwt)
        if header.get("alg") != "ES256" or not header.get("kid"):
            raise ValueError("unexpected algorithm or key id")
        response = _plaid_request(
            "/webhook_verification_key/get",
            payload={"key_id": str(header["kid"])},
            timeout=15,
        )
        response.raise_for_status()
        key = response.json()["key"]
        public_key = jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(key))
        claims = jwt.decode(
            signed_jwt,
            public_key,
            algorithms=["ES256"],
            options={"require": ["iat", "request_body_sha256"]},
            leeway=10,
        )
        issued_at = int(claims["iat"])
        if abs(int(datetime.now(timezone.utc).timestamp()) - issued_at) > 300:
            raise ValueError("webhook is outside the replay window")
        expected_hash = str(claims["request_body_sha256"])
        actual_hash = hashlib.sha256(raw_body).hexdigest()
        if not hmac.compare_digest(actual_hash, expected_hash):
            raise ValueError("webhook body hash mismatch")
    except Exception as exc:
        raise PlaidWebhookVerificationError("Plaid webhook verification failed") from exc


def process_plaid_webhook(db: Session, payload: dict) -> TradingAccount | None:
    """Record webhook state quickly; the worker performs the slower API sync."""
    environment = str(payload.get("environment") or "").lower()
    if environment and environment != get_settings().plaid_env.strip().lower():
        raise PlaidWebhookVerificationError("Plaid webhook environment does not match this deployment")
    account = portfolio_account_for_plaid_item(db, str(payload.get("item_id") or ""))
    if not account:
        return None
    connection = _connection(db, account)
    metadata = dict(connection.metadata_json or {})
    webhook_type = str(payload.get("webhook_type") or "")
    metadata["plaid_last_webhook_at"] = utcnow().isoformat()
    metadata["plaid_last_webhook"] = {
        "type": webhook_type,
        "code": payload.get("webhook_code"),
    }
    error = payload.get("error") or {}
    if error:
        connection.status = "ERROR"
        connection.error_code = str(error.get("error_code") or "PLAID_ITEM_ERROR")[:120]
        connection.error_message = str(error.get("error_message") or "Plaid reported an Item error")[:500]
    else:
        connection.status = "PENDING_REFRESH"
        connection.error_code = None
        connection.error_message = None
    connection.metadata_json = metadata
    db.commit()
    return account if not error and webhook_type in {"HOLDINGS", "INVESTMENTS_TRANSACTIONS", "TRANSACTIONS"} else None


def plaid_investment_transactions(
    db: Session,
    user: User,
    *,
    account_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    query = db.query(PortfolioInvestmentTransaction).filter_by(user_id=user.id, provider="plaid")
    if account_id:
        account = db.query(TradingAccount).filter_by(id=account_id, user_id=user.id, venue="PLAID").one_or_none()
        if not account:
            raise LookupError("Plaid portfolio account not found")
        query = query.filter_by(account_id=account.id)
    rows = query.order_by(PortfolioInvestmentTransaction.posted_date.desc(), PortfolioInvestmentTransaction.created_at.desc()).limit(max(1, min(limit, 250))).all()
    return [
        {
            "id": row.id,
            "account_id": row.account_id,
            "provider_account_id": row.provider_account_id,
            "date": row.posted_date.isoformat(),
            "transaction_datetime": row.transaction_datetime.isoformat() if row.transaction_datetime else None,
            "name": row.name,
            "symbol": row.symbol,
            "type": row.transaction_type,
            "subtype": row.subtype,
            "quantity": row.quantity,
            "price": row.price,
            "amount": row.amount,
            "fees": row.fees,
            "currency": row.currency,
            "cancelled": row.cancelled,
        }
        for row in rows
    ]


def _sync_ibkr(db: Session, account: TradingAccount) -> None:
    settings = get_settings()
    connection = _connection(db, account)
    stored = decrypt_token(connection.credential_ciphertext or "")
    token_payload = json.loads(stored) if stored.startswith("{") else {"access_token": stored}
    if int((connection.metadata_json or {}).get("expires_at") or 0) <= int(datetime.now(timezone.utc).timestamp()) + 60:
        refresh_token = token_payload.get("refresh_token")
        if not refresh_token or not settings.ibkr_oauth_token_url:
            raise RuntimeError("IBKR authorization expired; reconnect the account")
        refresh = requests.post(settings.ibkr_oauth_token_url, data={"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": settings.ibkr_client_id, "client_secret": settings.ibkr_client_secret}, timeout=20)
        refresh.raise_for_status()
        refreshed = refresh.json()
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = refresh_token
        token_payload = refreshed
        connection.credential_ciphertext = encrypt_token(json.dumps(token_payload))
        connection.metadata_json = {**(connection.metadata_json or {}), "expires_at": int(datetime.now(timezone.utc).timestamp()) + int(refreshed.get("expires_in") or 3600)}
        db.commit()
    token = token_payload["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    accounts_response = requests.get(f"{settings.ibkr_api_url.rstrip('/')}/portfolio/accounts", headers=headers, timeout=20)
    accounts_response.raise_for_status()
    accounts = accounts_response.json()
    if not accounts:
        raise RuntimeError("IBKR returned no portfolio accounts")
    total_equity = 0.0
    total_available = 0.0
    all_positions = []
    account_ids = []
    for item in accounts:
        account_id = item.get("accountId") or item.get("id")
        if not account_id:
            continue
        account_ids.append(account_id)
        summary_response = requests.get(f"{settings.ibkr_api_url.rstrip('/')}/portfolio/{account_id}/summary", headers=headers, timeout=20)
        summary_response.raise_for_status()
        summary = summary_response.json()
        net = summary.get("netliquidation", {})
        available = summary.get("availablefunds", {})
        total_equity += float(net.get("amount") or net.get("value") or 0)
        total_available += float(available.get("amount") or available.get("value") or 0)
        for page in range(100):
            positions_response = requests.get(f"{settings.ibkr_api_url.rstrip('/')}/portfolio/{account_id}/positions/{page}", headers=headers, timeout=20)
            positions_response.raise_for_status()
            page_positions = positions_response.json()
            if not page_positions:
                break
            all_positions.extend(page_positions)
    _save_snapshot(db, account, total_equity, total_available, {"account_ids": account_ids}, all_positions, "ibkr")


def _save_snapshot(db: Session, account: TradingAccount, equity: float, available: float, raw: dict, positions: list, provider: str, daily_pnl: float = 0.0) -> None:
    captured = utcnow()
    db.add(AccountSnapshot(user_id=account.user_id, account_id=account.id, balance=equity, equity=equity, available_margin=available, daily_pnl=daily_pnl, drawdown=0, exposure=max(equity - available, 0), stale=False, raw_event_reference={"provider": provider, "payload": raw}, captured_at=captured))
    for item in positions:
        position = item.get("position", item)
        quantity = _finite(position.get("szi") or position.get("quantity") or position.get("position") or 0)
        price = _finite(position.get("markPx") or position.get("price") or position.get("mktPrice") or 0)
        value = _finite(position.get("value") or position.get("mktValue") or quantity * price)
        meta = position.get("meta") if isinstance(position.get("meta"), dict) else {}
        db.add(PositionSnapshot(user_id=account.user_id, account_id=account.id, instrument=str(position.get("coin") or position.get("symbol") or position.get("contractDesc") or "UNKNOWN"), quantity=abs(quantity), side="LONG" if quantity >= 0 else "SHORT", average_price=_finite(position.get("entryPx") or position.get("cost") or position.get("avgCost") or price), mark_price=price, unrealized_pnl=_finite(position.get("unrealizedPnl") or position.get("unrealized_pnl") or 0), realized_pnl=0, leverage=_finite((position.get("leverage") or {}).get("value", 1) if isinstance(position.get("leverage"), dict) else position.get("leverage") or 1, 1.0), raw_event_reference={"provider": provider, "value": value, **meta}, captured_at=captured))
    connection = _connection(db, account)
    connection.last_health_at = captured
    connection.status = "CONNECTED"
    connection.error_code = None
    connection.error_message = None
    db.commit()


def _parse_instrument(instrument: str) -> tuple[str, str | None]:
    if " @ " in instrument:
        symbol, chain = instrument.rsplit(" @ ", 1)
        return symbol.strip(), chain.strip().lower() or None
    return instrument.strip(), None


def _asset_class(symbol: str, raw: dict) -> str:
    if raw.get("asset_class"):
        return str(raw["asset_class"])
    base = str(raw.get("base_symbol") or symbol).upper().strip()
    if base in _STABLECOIN_SYMBOLS:
        return "stablecoin"
    if base in _EQUITY_PROXY_SYMBOLS:
        return "equity"
    if raw.get("chain") or raw.get("native"):
        return "crypto"
    if str(raw.get("provider") or "").lower() in {"plaid", "ibkr"}:
        return "equity"
    return "crypto"


def _latest_positions(db: Session, user_id: str, account: TradingAccount, snapshot: AccountSnapshot) -> list[PositionSnapshot]:
    exact = db.query(PositionSnapshot).filter_by(
        user_id=user_id,
        account_id=account.id,
        captured_at=snapshot.captured_at,
    ).all()
    if exact:
        return exact
    # Older snapshots created before captured_at was consistently shared by the
    # account and position rows may have database precision drift. Keep a small
    # compatibility window without double-counting newer repeated syncs.
    return db.query(PositionSnapshot).filter(
        PositionSnapshot.user_id == user_id,
        PositionSnapshot.account_id == account.id,
        PositionSnapshot.captured_at >= snapshot.captured_at - timedelta(seconds=2),
        PositionSnapshot.captured_at <= snapshot.captured_at + timedelta(seconds=2),
    ).all()


def _position_value(row: PositionSnapshot) -> float:
    return abs(float((row.raw_event_reference or {}).get("value") or row.quantity * row.mark_price))


def _holding_from_position(row: PositionSnapshot, nav: float) -> dict:
    raw = row.raw_event_reference or {}
    symbol, parsed_chain = _parse_instrument(row.instrument)
    chain = str(raw.get("chain") or parsed_chain or "") or None
    value = _position_value(row)
    return {
        "symbol": symbol,
        "instrument": row.instrument,
        "name": str(raw.get("name") or symbol),
        "chain": chain,
        "quantity": float(row.quantity),
        "price": float(row.mark_price),
        "value": round(value, 2),
        "weight": round(value / nav, 6) if nav > 0 else 0.0,
        "change_24h": round(float(raw.get("change_24h") or 0), 2),
        "change_24h_pct": round(float(raw.get("change_24h_pct") or 0), 4),
        "asset_class": _asset_class(symbol, raw),
        "native": bool(raw.get("native")),
        "verified": bool(raw.get("verified", True)),
        "priced": bool(raw.get("priced", value > 0)),
        "logo": raw.get("logo"),
    }


def _aggregate_holdings(db: Session, user_id: str, accounts: list[TradingAccount], latest_snapshots: list[AccountSnapshot], *, limit: int | None = None) -> list[dict]:
    nav = sum(float(row.equity) for row in latest_snapshots)
    merged: dict[str, dict] = {}
    for account in accounts:
        snapshot = next((row for row in latest_snapshots if row.account_id == account.id), None)
        if not snapshot:
            continue
        for position in _latest_positions(db, user_id, account, snapshot):
            holding = _holding_from_position(position, nav)
            key = holding["instrument"].upper()
            existing = merged.get(key)
            if existing:
                existing["value"] = round(existing["value"] + holding["value"], 2)
                existing["quantity"] += holding["quantity"]
                existing["change_24h"] = round(existing["change_24h"] + holding["change_24h"], 2)
                existing["weight"] = round(existing["value"] / nav, 6) if nav > 0 else 0.0
            else:
                merged[key] = holding
    ranked = sorted(merged.values(), key=lambda item: item["value"], reverse=True)
    return ranked[:limit] if limit else ranked


def _asset_class_totals(holdings: list[dict]) -> dict:
    totals: dict[str, float] = {}
    for holding in holdings:
        key = holding.get("asset_class") or "other"
        totals[key] = round(totals.get(key, 0.0) + float(holding.get("value") or 0), 2)
    return totals


def portfolio_view(db: Session, user: User) -> dict:
    settings = get_settings()
    plaid_configured = bool(
        settings.plaid_client_id
        and settings.plaid_secret
        and settings.plaid_env.strip().lower() in {"sandbox", "production"}
        and (settings.plaid_env.strip().lower() == "sandbox" or settings.plaid_redirect_uri.startswith("https://"))
    )
    accounts = db.query(TradingAccount).filter(TradingAccount.user_id == user.id, TradingAccount.account_type == "READ_ONLY", TradingAccount.status == "ACTIVE").all()
    latest = []
    all_rows = []
    for account in accounts:
        rows = list(reversed(db.query(AccountSnapshot).filter_by(user_id=user.id, account_id=account.id).order_by(AccountSnapshot.captured_at.desc()).limit(1_500).all()))
        all_rows.extend(rows)
        if rows:
            latest.append(rows[-1])
    timeline = []
    latest_by_account = {}
    account_ids = {account.id for account in accounts}
    for row in sorted(all_rows, key=lambda item: item.captured_at):
        latest_by_account[row.account_id] = row
        if set(latest_by_account) == account_ids:
            timeline.append({"date": row.captured_at.astimezone(timezone.utc).isoformat(), "nav": sum(item.equity for item in latest_by_account.values())})
    if len(timeline) > 500:
        step = max(1, len(timeline) // 499)
        timeline = timeline[::step]
        final_point = {"date": max(all_rows, key=lambda item: item.captured_at).captured_at.astimezone(timezone.utc).isoformat(), "nav": sum(row.equity for row in latest)}
        if timeline[-1]["date"] != final_point["date"]:
            timeline.append(final_point)
    connections = []
    account_summaries = []
    for account in accounts:
        connection = _connection(db, account)
        snapshot = next((row for row in latest if row.account_id == account.id), None)
        effective_status = "STALE" if snapshot and _snapshot_is_stale(account, snapshot) else connection.status
        metadata = connection.metadata_json or {}
        connections.append(
            {
                "id": account.id,
                "provider": account.venue.lower(),
                "name": account.name,
                "status": effective_status,
                "last_sync": connection.last_health_at.isoformat() if connection.last_health_at else None,
                "error": connection.error_message,
                "can_refresh": account.venue == "PLAID" and plaid_configured and metadata.get("plaid_refresh_supported") is not False,
                "refresh_requested_at": metadata.get("plaid_refresh_requested_at"),
            }
        )
        account_summaries.append({
            "id": account.id,
            "provider": account.venue.lower(),
            "name": account.name,
            "status": effective_status,
            "nav": round(float(snapshot.equity), 2) if snapshot else 0.0,
            "available_cash": round(float(snapshot.available_margin), 2) if snapshot else 0.0,
            "daily_change": round(float(snapshot.daily_pnl), 2) if snapshot else 0.0,
            "as_of": snapshot.captured_at.astimezone(timezone.utc).isoformat() if snapshot else None,
        })
    data_as_of = min((row.captured_at for row in latest), default=None)
    nav = sum(row.equity for row in latest)
    daily_change = sum(float(row.daily_pnl) for row in latest)
    previous_nav = nav - daily_change
    holdings = _aggregate_holdings(db, user.id, accounts, latest, limit=50)
    return {
        "connected": bool(latest),
        "stale": any(_snapshot_is_stale(account, next(row for row in latest if row.account_id == account.id)) for account in accounts if any(row.account_id == account.id for row in latest)),
        "data_as_of": data_as_of.isoformat() if data_as_of else None,
        "nav": nav,
        "available_cash": sum(row.available_margin for row in latest),
        "daily_change": round(daily_change, 2),
        "daily_change_pct": round(daily_change / previous_nav * 100, 4) if previous_nav > 0 else None,
        "nav_history": timeline,
        "holdings": holdings,
        "asset_classes": _asset_class_totals(holdings),
        "accounts": account_summaries,
        "connections": connections,
        "providers": {
            "plaid": plaid_configured,
            "plaid_refresh": plaid_configured,
            "plaid_cash_transactions": plaid_configured and bool(getattr(settings, "plaid_cash_transactions_enabled", False)),
            "plaid_webhooks": bool(getattr(settings, "plaid_webhook_url", "")),
            "ibkr": bool(
                getattr(settings, "ibkr_oauth_authorize_url", "")
                and getattr(settings, "ibkr_oauth_token_url", "")
                and getattr(settings, "ibkr_client_id", "")
                and getattr(settings, "ibkr_client_secret", "")
            ),
            "hyperliquid": True,
            "evm": bool(settings.moralis_api_key),
            # Private CEX connectors use per-user read-only keys, so they are
            # always offerable (no server-side credential is required).
            "binance": True,
            "okx": True,
            "bybit": True,
        },
    }


def portfolio_context(db: Session, user_id: str, *, detailed: bool = False) -> dict:
    accounts = db.query(TradingAccount).filter_by(user_id=user_id, account_type="READ_ONLY", status="ACTIVE").all()
    latest_snapshots: list[AccountSnapshot] = []
    missing: list[str] = []
    stale = False
    for account in accounts:
        snapshot = db.query(AccountSnapshot).filter_by(user_id=user_id, account_id=account.id).order_by(AccountSnapshot.captured_at.desc()).first()
        if not snapshot:
            missing.append(f"{account.name}: no synchronized account snapshot")
            continue
        latest_snapshots.append(snapshot)
        stale = stale or _snapshot_is_stale(account, snapshot)
    nav = sum(float(row.equity) for row in latest_snapshots)
    holdings_full = _aggregate_holdings(db, user_id, accounts, latest_snapshots)
    ranked_holdings = holdings_full[: (20 if detailed else 8)]
    holdings = [
        {
            "symbol": item["symbol"],
            "chain": item["chain"],
            "value": item["value"],
            "weight": item["weight"],
            "price": item["price"],
            "quantity": round(item["quantity"], 8),
            "change_24h": item["change_24h"],
            "change_24h_pct": item["change_24h_pct"],
            "asset_class": item["asset_class"],
        }
        for item in ranked_holdings
    ]
    concentration = sum(item["weight"] ** 2 for item in holdings)
    class_totals = _asset_class_totals(holdings_full)
    crypto = round(sum(item["value"] for item in holdings_full if item["asset_class"] in {"crypto", "stablecoin"}), 2)
    equity = round(sum(item["value"] for item in holdings_full if item["asset_class"] == "equity"), 2)
    duplicate_exposure = sorted({item["symbol"] for item in holdings_full if item["symbol"].upper() in {"BTC", "MSTR", "IBIT"}})
    daily_change = round(sum(float(row.daily_pnl) for row in latest_snapshots), 2)
    previous_nav = nav - daily_change
    data_as_of = min((row.captured_at for row in latest_snapshots), default=None)
    account_summaries = [
        {
            "id": account.id,
            "name": account.name,
            "provider": account.venue.lower(),
            "nav": round(float(snapshot.equity), 2),
            "available_cash": round(float(snapshot.available_margin), 2),
            "daily_change": round(float(snapshot.daily_pnl), 2),
            "as_of": snapshot.captured_at.astimezone(timezone.utc).isoformat(),
        }
        for account in accounts
        for snapshot in latest_snapshots
        if snapshot.account_id == account.id
    ]
    if not accounts:
        missing.append("No real portfolio account is connected")
    return {
        "connected": bool(latest_snapshots),
        "portfolio_ids": [account.id for account in accounts],
        "data_as_of": data_as_of.astimezone(timezone.utc).isoformat() if data_as_of else None,
        "total_nav": round(nav, 2) if latest_snapshots else None,
        "daily_change": daily_change if latest_snapshots else None,
        "daily_change_pct": round(daily_change / previous_nav * 100, 4) if latest_snapshots and previous_nav > 0 else None,
        "top_holdings": holdings,
        "holding_count": len(holdings_full),
        "concentration_hhi": round(concentration, 6) if holdings else None,
        "asset_class_exposure": {"crypto": crypto, "equity": equity} if holdings_full else {},
        "asset_classes": class_totals,
        "accounts": account_summaries,
        "duplicate_exposure": duplicate_exposure,
        "stale": stale,
        "missing_data": missing,
    }


DEFAULT_AUTOPILOT = {"enabled": False, "cadence": "daily", "auto_sync": True, "risk_alerts": True, "long_gamma_watch": True, "delivery": "in_app", "skill_refs": []}


def autopilot_view(db: Session, user: User) -> dict:
    preference = db.query(UserPreference).filter_by(user_id=user.id).one_or_none()
    config = {**DEFAULT_AUTOPILOT, **((preference.portfolio_autopilot_json if preference else {}) or {})}
    accounts = db.query(TradingAccount).filter_by(user_id=user.id, account_type="READ_ONLY", status="ACTIVE").all()
    latest_review = db.query(PortfolioAutopilotReview).filter_by(user_id=user.id).order_by(PortfolioAutopilotReview.created_at.desc()).first()
    findings = list(latest_review.findings_json or []) if latest_review else []
    for account in accounts:
        latest = db.query(AccountSnapshot).filter_by(user_id=user.id, account_id=account.id).order_by(AccountSnapshot.captured_at.desc()).first()
        if not latest and not latest_review:
            findings.append({"severity": "warning", "title": f"{account.name}: no synchronized snapshot"})
        elif latest and latest.stale and not latest_review:
            findings.append({"severity": "warning", "title": f"{account.name}: snapshot is stale"})
    return {"config": config, "account_count": len(accounts), "findings": findings, "concentration": latest_review.concentration_json if latest_review else {}, "execution": "RESEARCH_ONLY", "last_review": latest_review.created_at.isoformat() if latest_review else None}


def update_autopilot(db: Session, user: User, payload: dict) -> dict:
    preference = db.query(UserPreference).filter_by(user_id=user.id).one_or_none()
    if not preference:
        preference = UserPreference(user_id=user.id)
        db.add(preference)
    config = {**DEFAULT_AUTOPILOT, **(preference.portfolio_autopilot_json or {})}
    for key in DEFAULT_AUTOPILOT:
        if key in payload:
            config[key] = payload[key]
    if config["cadence"] not in {"daily", "weekly"} or config["delivery"] not in {"in_app", "telegram", "imessage"} or not isinstance(config["skill_refs"], list) or len(config["skill_refs"]) > 8:
        raise ValueError("Unsupported Autopilot configuration")
    preference.portfolio_autopilot_json = config
    db.commit()
    return autopilot_view(db, user)


def run_autopilot_review(db: Session, user: User) -> dict:
    preference = db.query(UserPreference).filter_by(user_id=user.id).one_or_none()
    config = {**DEFAULT_AUTOPILOT, **((preference.portfolio_autopilot_json if preference else {}) or {})}
    accounts = db.query(TradingAccount).filter_by(user_id=user.id, account_type="READ_ONLY", status="ACTIVE").all()
    if not accounts:
        raise ValueError("Connect at least one portfolio account first")
    latest_snapshots = []
    values_by_asset: dict[str, float] = {}
    findings = []
    data_as_of = None
    for account in accounts:
        snapshot = db.query(AccountSnapshot).filter_by(user_id=user.id, account_id=account.id).order_by(AccountSnapshot.captured_at.desc()).first()
        if not snapshot:
            findings.append({"severity": "warning", "title": f"{account.name}: no synchronized snapshot"})
            continue
        latest_snapshots.append(snapshot)
        data_as_of = max(filter(None, [data_as_of, snapshot.captured_at])) if data_as_of else snapshot.captured_at
        age = datetime.now(timezone.utc) - snapshot.captured_at.astimezone(timezone.utc)
        if config.get("risk_alerts", True) and _snapshot_is_stale(account, snapshot):
            findings.append({"severity": "warning", "title": f"{account.name}: data is {int(age.total_seconds() // 60)} minutes old"})
        positions = db.query(PositionSnapshot).filter_by(user_id=user.id, account_id=account.id, captured_at=snapshot.captured_at).all()
        for position in positions:
            value = abs(float((position.raw_event_reference or {}).get("value") or position.quantity * position.mark_price))
            values_by_asset[position.instrument] = values_by_asset.get(position.instrument, 0) + value
    nav = sum(item.equity for item in latest_snapshots)
    concentration = {asset: round(value / nav, 4) for asset, value in values_by_asset.items()} if nav > 0 else {}
    for asset, weight in sorted(concentration.items(), key=lambda item: item[1], reverse=True):
        if config.get("risk_alerts", True) and weight >= 0.35:
            findings.append({"severity": "high", "title": f"{asset} concentration is {weight:.1%}"})
    if config.get("long_gamma_watch", True):
        try:
            from apps.api.services.options_service import get_option_chain
            from packages.options.long_gamma import discover_long_gamma

            chain = get_option_chain("BTC")
            candidates = discover_long_gamma(chain.get("instruments", []), 3) if chain.get("status") == "HEALTHY" else []
            if candidates:
                instrument = candidates[0].get("instrument_name") or candidates[0].get("instrument") or "BTC option structure"
                findings.append({"severity": "info", "title": f"Long Gamma Watch: {instrument} is available for research review"})
        except Exception:
            findings.append({"severity": "warning", "title": "Long Gamma Watch data is currently unavailable"})
    if not findings:
        findings.append({"severity": "info", "title": "No freshness or concentration exception detected"})
    review = PortfolioAutopilotReview(user_id=user.id, nav=nav, account_count=len(accounts), findings_json=findings, concentration_json=concentration, status="COMPLETED", data_as_of=data_as_of)
    db.add(review)
    db.commit()
    return autopilot_view(db, user)


def disconnect_account(db: Session, user: User, account: TradingAccount) -> None:
    if account.user_id != user.id or account.account_type != "READ_ONLY":
        raise LookupError("Portfolio account not found")
    connection = _connection(db, account)
    connection.status = "DISCONNECTED"
    connection.credential_ciphertext = None
    connection.error_code = None
    connection.error_message = None
    account.status = "DISCONNECTED"
    db.commit()
