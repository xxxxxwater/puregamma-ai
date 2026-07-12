from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import requests
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import AccountSnapshot, ExchangeConnection, PortfolioAutopilotReview, PositionSnapshot, TradingAccount, User, UserPreference, utcnow


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


def plaid_link_token(user: User) -> str:
    settings = get_settings()
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise RuntimeError("Plaid Investments is not configured")
    base = f"https://{settings.plaid_env}.plaid.com"
    response = requests.post(f"{base}/link/token/create", json={"client_id": settings.plaid_client_id, "secret": settings.plaid_secret, "client_name": "PureGamma AI", "language": "en", "country_codes": ["US", "CA"], "user": {"client_user_id": user.id}, "products": ["investments"], "redirect_uri": settings.plaid_redirect_uri}, timeout=15)
    response.raise_for_status()
    return response.json()["link_token"]


def connect_plaid(db: Session, user: User, public_token: str, institution_name: str = "Plaid Investments") -> TradingAccount:
    settings = get_settings()
    base = f"https://{settings.plaid_env}.plaid.com"
    response = requests.post(f"{base}/item/public_token/exchange", json={"client_id": settings.plaid_client_id, "secret": settings.plaid_secret, "public_token": public_token}, timeout=15)
    response.raise_for_status()
    payload = response.json()
    return _account(db, user, "PLAID", institution_name, {"item_id": payload.get("item_id")}, payload["access_token"])


def connect_hyperliquid(db: Session, user: User, address: str) -> TradingAccount:
    normalized = address.strip().lower()
    if not normalized.startswith("0x") or len(normalized) != 42 or any(ch not in "0123456789abcdef" for ch in normalized[2:]):
        raise ValueError("Invalid Hyperliquid wallet address")
    return _account(db, user, "HYPERLIQUID", "Hyperliquid", {"wallet_address": normalized})


def connect_ibkr_token(db: Session, user: User, token_payload: dict) -> TradingAccount:
    metadata = {"expires_at": int(datetime.now(timezone.utc).timestamp()) + int(token_payload.get("expires_in") or 3600)}
    return _account(db, user, "IBKR", "Interactive Brokers", metadata, json.dumps(token_payload))


def sync_account(db: Session, user: User, account: TradingAccount) -> None:
    if account.user_id != user.id:
        raise LookupError("Account not found")
    try:
        if account.venue == "HYPERLIQUID":
            _sync_hyperliquid(db, account)
        elif account.venue == "PLAID":
            _sync_plaid(db, account)
        elif account.venue == "IBKR":
            _sync_ibkr(db, account)
        else:
            raise ValueError("Unsupported portfolio provider")
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


def _sync_plaid(db: Session, account: TradingAccount) -> None:
    settings = get_settings()
    connection = _connection(db, account)
    token = decrypt_token(connection.credential_ciphertext or "")
    response = requests.post(f"https://{settings.plaid_env}.plaid.com/investments/holdings/get", json={"client_id": settings.plaid_client_id, "secret": settings.plaid_secret, "access_token": token}, timeout=30)
    response.raise_for_status()
    data = response.json()
    securities = {item["security_id"]: item for item in data.get("securities", [])}
    positions = []
    for holding in data.get("holdings", []):
        security = securities.get(holding.get("security_id"), {})
        positions.append({"symbol": security.get("ticker_symbol") or security.get("name") or "UNKNOWN", "quantity": holding.get("quantity", 0), "price": holding.get("institution_price", 0), "value": holding.get("institution_value", 0), "cost": holding.get("cost_basis", 0)})
    equity = sum(float(item.get("balances", {}).get("current") or 0) for item in data.get("accounts", []))
    available = sum(float(item.get("balances", {}).get("available") or 0) for item in data.get("accounts", []))
    _save_snapshot(db, account, equity, available, {"request_id": data.get("request_id")}, positions, "plaid")


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


def _save_snapshot(db: Session, account: TradingAccount, equity: float, available: float, raw: dict, positions: list, provider: str) -> None:
    captured = utcnow()
    db.add(AccountSnapshot(user_id=account.user_id, account_id=account.id, balance=equity, equity=equity, available_margin=available, daily_pnl=0, drawdown=0, exposure=max(equity - available, 0), stale=False, raw_event_reference={"provider": provider, "payload": raw}, captured_at=captured))
    for item in positions:
        position = item.get("position", item)
        quantity = float(position.get("szi") or position.get("quantity") or position.get("position") or 0)
        price = float(position.get("markPx") or position.get("price") or position.get("mktPrice") or 0)
        value = float(position.get("value") or position.get("mktValue") or quantity * price)
        db.add(PositionSnapshot(user_id=account.user_id, account_id=account.id, instrument=str(position.get("coin") or position.get("symbol") or position.get("contractDesc") or "UNKNOWN"), quantity=abs(quantity), side="LONG" if quantity >= 0 else "SHORT", average_price=float(position.get("entryPx") or position.get("cost") or position.get("avgCost") or price), mark_price=price, unrealized_pnl=float(position.get("unrealizedPnl") or position.get("unrealized_pnl") or 0), realized_pnl=0, leverage=float((position.get("leverage") or {}).get("value", 1) if isinstance(position.get("leverage"), dict) else position.get("leverage") or 1), raw_event_reference={"provider": provider, "value": value}, captured_at=captured))
    connection = _connection(db, account)
    connection.last_health_at = captured
    connection.status = "CONNECTED"
    connection.error_code = None
    connection.error_message = None
    db.commit()


def portfolio_view(db: Session, user: User) -> dict:
    accounts = db.query(TradingAccount).filter(TradingAccount.user_id == user.id, TradingAccount.account_type == "READ_ONLY", TradingAccount.status == "ACTIVE").all()
    latest = []
    all_rows = []
    for account in accounts:
        rows = list(reversed(db.query(AccountSnapshot).filter_by(user_id=user.id, account_id=account.id).order_by(AccountSnapshot.captured_at.desc()).limit(10_000).all()))
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
    for account in accounts:
        connection = _connection(db, account)
        snapshot = next((row for row in latest if row.account_id == account.id), None)
        effective_status = "STALE" if snapshot and _snapshot_is_stale(account, snapshot) else connection.status
        connections.append({"id": account.id, "provider": account.venue.lower(), "name": account.name, "status": effective_status, "last_sync": connection.last_health_at.isoformat() if connection.last_health_at else None, "error": connection.error_message})
    data_as_of = min((row.captured_at for row in latest), default=None)
    return {"connected": bool(latest), "stale": any(_snapshot_is_stale(account, next(row for row in latest if row.account_id == account.id)) for account in accounts if any(row.account_id == account.id for row in latest)), "data_as_of": data_as_of.isoformat() if data_as_of else None, "nav": sum(row.equity for row in latest), "available_cash": sum(row.available_margin for row in latest), "nav_history": timeline, "connections": connections, "providers": {"plaid": True, "ibkr": True, "hyperliquid": True}}


DEFAULT_AUTOPILOT = {"enabled": False, "cadence": "daily", "auto_sync": True, "risk_alerts": True, "long_gamma_watch": True, "delivery": "in_app"}


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
    if config["cadence"] not in {"daily", "weekly"} or config["delivery"] not in {"in_app", "telegram", "imessage"}:
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
