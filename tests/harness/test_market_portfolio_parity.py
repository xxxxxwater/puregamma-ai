"""Legacy-vs-Harness parity for Market Data and Portfolio (retirement evidence).

Two halves share one fixture:

1. Golden: the real FastAPI ``GET /portfolio`` and ``GET /market/snapshot``
   responses for fixed scenarios (frozen clock, explicit ids) must equal
   ``harness/scripts/fixtures/legacy-parity.json``. The Harness side
   (``harness/scripts/market-portfolio-parity.test.mjs``, part of
   ``pnpm run check``) replays exactly these responses through the real
   compatibility providers and tools. Regenerate with
   ``PG_UPDATE_PARITY_FIXTURES=1`` after an intentional legacy change.
2. Live: when the Harness workspace is installed, FastAPI is served on a
   loopback port and the real providers/tools run against it over HTTP with a
   per-user token file; their output is compared field by field here.

The parity rules (fields, freshness, unavailable semantics, NAV never shown as
0 when missing) are asserted on both halves.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.dependencies import create_access_token, get_db
from apps.api.main import app
from apps.api.routers import market as market_router
from apps.api.services import portfolio_service
from packages.data.base import MarketQuote
from packages.database.models import (
    AccountSnapshot,
    ExchangeConnection,
    PositionSnapshot,
    TradingAccount,
    User,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "harness" / "scripts" / "fixtures" / "legacy-parity.json"
HARNESS_READS = ROOT / "harness" / "scripts" / "parity" / "harness-reads.mjs"
TSX = ROOT / "harness" / "node_modules" / ".bin" / "tsx"
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _user(db, email: str) -> User:
    user = User(id=f"user-{email.split('@')[0]}", email=email, name=email.split("@")[0], role="user", plan="Pro", credit_balance=100)
    db.add(user)
    db.flush()
    return user


def _account(db, user: User, account_id: str, venue: str, name: str, *, last_health: str) -> TradingAccount:
    account = TradingAccount(id=account_id, user_id=user.id, name=name, venue=venue, account_type="READ_ONLY", base_currency="USD", status="ACTIVE", permissions_json={"read_positions": True, "trade": False})
    db.add(account)
    db.flush()
    db.add(ExchangeConnection(id=f"conn-{account_id}", user_id=user.id, account_id=account.id, adapter=venue.lower(), environment="production", status="CONNECTED", last_health_at=_at(last_health), metadata_json={}))
    return account


def _snapshot(db, account: TradingAccount, *, equity: float, cash: float, at: str, pnl: float = 0.0) -> None:
    db.add(AccountSnapshot(id=f"snap-{account.id}", user_id=account.user_id, account_id=account.id, balance=equity, equity=equity, available_margin=cash, daily_pnl=pnl, drawdown=0, exposure=max(equity - cash, 0), stale=False, raw_event_reference={"provider": account.venue.lower(), "payload": {}}, captured_at=_at(at)))


def _position(db, account: TradingAccount, instrument: str, *, quantity: float, side: str, mark: float, pnl: float, at: str) -> None:
    db.add(PositionSnapshot(id=f"pos-{account.id}-{instrument}", user_id=account.user_id, account_id=account.id, instrument=instrument, quantity=quantity, side=side, average_price=mark, mark_price=mark, unrealized_pnl=pnl, captured_at=_at(at)))


def _seed(db) -> dict[str, User]:
    connected = _user(db, "parity-connected@puregamma.ai")
    hl = _account(db, connected, "acct-hl", "HYPERLIQUID", "Perps", last_health="2026-10-29T11:55:00+00:00")
    _snapshot(db, hl, equity=12500.25, cash=2500.5, at="2026-10-29T11:55:00+00:00", pnl=120.0)
    _position(db, hl, "BTC", quantity=0.25, side="long", mark=64000.5, pnl=310.75, at="2026-10-29T11:55:00+00:00")
    _position(db, hl, "ETH", quantity=-3.0, side="short", mark=2500.0, pnl=-42.1, at="2026-10-29T11:55:00+00:00")
    plaid = _account(db, connected, "acct-plaid", "PLAID", "Brokerage", last_health="2026-10-27T10:00:00+00:00")
    # Older than the 36 h Plaid window: stale on both sides.
    _snapshot(db, plaid, equity=40000.0, cash=1000.0, at="2026-10-27T10:00:00+00:00")

    partial = _user(db, "parity-partial@puregamma.ai")
    ibkr = _account(db, partial, "acct-ibkr", "IBKR", "IBKR", last_health="2026-10-29T11:58:00+00:00")
    _snapshot(db, ibkr, equity=8000.0, cash=500.0, at="2026-10-29T11:58:00+00:00")
    # Connected but never synced: legacy reports nav/available_cash 0.0 with as_of null.
    _account(db, partial, "acct-evm", "EVM", "Wallet", last_health="2026-10-29T11:59:00+00:00")

    none = _user(db, "parity-none@puregamma.ai")
    db.commit()
    return {"connected": connected, "partial": partial, "none": none}


def _quote(symbol: str, price: float, at: str, *, source: str, realtime: bool, asset_type: str = "crypto") -> MarketQuote:
    return MarketQuote(symbol=symbol, price=price, volume_24h=1_000_000.0, market_cap=0.0, funding_rate=0.0, open_interest=0.0, volatility=0.0, liquidation_estimate=0.0, sentiment_score=0.0, timestamp=_at(at), source=source, source_symbol=symbol, change_24h=None, is_realtime=realtime, fallback_reason=None if realtime else "fallback", asset_type=asset_type)


MARKET = {
    "live": [
        _quote("BTC", 64000.5, "2026-10-29T11:59:30+00:00", source="coinbase", realtime=True),
        _quote("ETH", 2500.25, "2026-10-29T11:40:00+00:00", source="kraken", realtime=False),
        _quote("AAPL", 230.1, "2026-10-29T11:59:00+00:00", source="polygon", realtime=True, asset_type="equity"),
    ],
    "mock": [_quote("BTC", 50000.0, "2026-10-29T12:00:00+00:00", source="mock", realtime=False)],
}


@pytest.fixture()
def parity(db, monkeypatch):
    # SQLite returns naive datetimes and FastAPI's .astimezone() reads them in
    # the process zone; pin UTC so the golden bytes do not depend on the box.
    # (The Harness side is checked under a non-UTC zone separately.)
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    monkeypatch.setattr(portfolio_service, "datetime", FrozenDatetime)
    monkeypatch.setattr(market_router.market_cache, "get", lambda key: None)
    monkeypatch.setattr(market_router.market_cache, "set", lambda key, value, ttl_seconds=None: None)
    scenario = {"market": "live"}

    class FakeProvider:
        def __init__(self, mode: str = "auto") -> None:
            self.mode = mode

        def get_snapshot(self, symbols):
            return list(MARKET[scenario["market"]])

    monkeypatch.setattr(market_router, "PublicMarketDataProvider", FakeProvider)
    users = _seed(db)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    yield users, scenario
    app.dependency_overrides.clear()
    monkeypatch.undo()
    time.tzset()


def _legacy(users, scenario) -> dict:
    from fastapi.testclient import TestClient

    client = TestClient(app)
    out: dict = {"frozenNow": NOW.isoformat(), "portfolio": {}, "market": {}}
    for name, user in users.items():
        response = client.get("/portfolio", headers={"Authorization": f"Bearer {create_access_token(user)}"})
        assert response.status_code == 200, response.text
        out["portfolio"][name] = response.json()
    for name in MARKET:
        scenario["market"] = name
        response = client.get("/market/snapshot")
        assert response.status_code == 200, response.text
        out["market"][name] = response.json()
    scenario["market"] = "live"
    return out


def test_legacy_responses_match_the_golden_fixture(parity):
    users, scenario = parity
    legacy = _legacy(users, scenario)
    if os.environ.get("PG_UPDATE_PARITY_FIXTURES") == "1":
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(legacy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    golden = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert legacy == golden, "FastAPI changed; review the diff, then PG_UPDATE_PARITY_FIXTURES=1 and re-run the Harness parity check"


def test_legacy_semantics_the_harness_must_not_inherit(parity):
    """Pin the legacy behaviours the Harness deliberately does differently."""
    users, scenario = parity
    legacy = _legacy(users, scenario)
    none = legacy["portfolio"]["none"]
    assert none["connected"] is False and none["nav"] == 0, "legacy reports NAV 0 with connected=false"
    evm = next(row for row in legacy["portfolio"]["partial"]["accounts"] if row["id"] == "acct-evm")
    assert evm["as_of"] is None and evm["nav"] == 0.0 and evm["available_cash"] == 0.0, "legacy reports 0 for a never-synced account"
    assert legacy["market"]["mock"]["assets"][0]["is_mock"] is True


def _serve(port: int) -> threading.Thread:
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.05)
    thread.server = server  # type: ignore[attr-defined]
    return thread


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _harness(base_url: str, token_file: Path, *account_ids: str) -> dict:
    result = subprocess.run([str(TSX), str(HARNESS_READS), base_url, str(token_file), *account_ids], cwd=ROOT / "harness", capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout)


def _utc(value: str) -> str:
    """Legacy times are UTC; SQLite drops the offset, so a naive value is UTC too."""
    parsed = datetime.fromisoformat(value)
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC).isoformat().replace("+00:00", ".000Z")


def _same(harness_value, legacy_value) -> bool:
    """Same number: JSON 3.0 reaches JavaScript as 3, and the Harness string is "3"."""
    return isinstance(harness_value, str) and Decimal(harness_value) == Decimal(str(legacy_value))


@pytest.mark.skipif(not TSX.exists() or shutil.which("node") is None, reason="Harness workspace not installed (cd harness && pnpm install --frozen-lockfile)")
def test_live_fastapi_and_harness_agree(parity, tmp_path):
    users, scenario = parity
    legacy = _legacy(users, scenario)
    port = _free_port()
    server = _serve(port)
    base_url = f"http://127.0.0.1:{port}"
    try:
        reads = {}
        for name, user in users.items():
            token_file = tmp_path / f"{name}.token"
            token_file.write_text(create_access_token(user))
            token_file.chmod(0o600)
            reads[name] = _harness(base_url, token_file)
        token_file = tmp_path / "connected.token"
        filtered = _harness(base_url, token_file, "acct-hl")
    finally:
        server.server.should_exit = True  # type: ignore[attr-defined]
        server.join(timeout=10)

    # Connected: every field the tools report is the legacy value, as a decimal string.
    conn, conn_legacy = reads["connected"], legacy["portfolio"]["connected"]
    nav = conn["portfolioNavTool"]["value"]
    assert nav["available"] is True
    assert _same(nav["nav"], conn_legacy["nav"])
    assert _same(nav["cash"], conn_legacy["available_cash"])
    assert nav["stale"] is conn_legacy["stale"] is True, "the stale Plaid snapshot keeps both sides stale"
    assert nav["calculatedAt"] == _utc(conn_legacy["data_as_of"])
    accounts = {row["id"]: row for row in conn["portfolioSnapshotTool"]["value"]["accounts"]}
    for row in conn_legacy["accounts"]:
        assert accounts[row["id"]]["provider"] == row["provider"]
        assert accounts[row["id"]]["label"] == row["name"]
        assert accounts[row["id"]]["status"] == row["status"]
    positions = {(row["instrument"], row["side"]): row for row in conn["portfolioSnapshotTool"]["value"]["positions"]}
    for row in conn_legacy["positions"]:
        mine = positions[(row["symbol"], row["side"])]
        assert _same(mine["quantity"], row["quantity"])
        assert _same(mine["markPrice"], row["mark_price"])
        assert _same(mine["unrealizedPnl"], row["unrealized_pnl"])
        assert mine["source"] == f"compatibility:{row['venue']}"
    assert _same(conn["portfolioNavTool"]["meta"]["nav"], conn_legacy["nav"])

    # Filtered: NAV is that account's own figure, not the all-account total.
    hl_legacy = next(row for row in conn_legacy["accounts"] if row["id"] == "acct-hl")
    assert _same(filtered["portfolioNavTool"]["value"]["nav"], hl_legacy["nav"])
    assert filtered["portfolioNavTool"]["value"]["stale"] is False

    # Partial: the never-synced account is not a zero balance.
    partial = reads["partial"]
    assert _same(partial["portfolioNavTool"]["value"]["nav"], legacy["portfolio"]["partial"]["nav"])
    assert "without a snapshot" in partial["portfolioNavTool"]["value"]["reason"]
    assert [row["accountId"] for row in partial["portfolioService"]["cash"]] == ["acct-ibkr"]

    # None: unavailable with a reason on every surface; legacy's 0 never appears.
    none = reads["none"]
    assert none["portfolioNavTool"]["value"]["available"] is False
    assert "nav" not in none["portfolioNavTool"]["value"]
    assert none["portfolioNavTool"]["meta"]["nav"] is None
    assert none["portfolioNavTool"]["text"].startswith("NAV unavailable")
    assert none["portfolioSnapshotTool"]["meta"]["available"] is False

    # Market: same symbols, prices, times and sources; non-realtime is stale.
    quotes = {row["symbol"]: row for row in conn["marketSnapshotTool"]["value"]["quotes"]}
    for asset in legacy["market"]["live"]["assets"]:
        mine = quotes[asset["symbol"]]
        assert _same(mine["last"], asset["price"])
        assert mine["observedAt"] == asset["timestamp"]
        assert mine["source"] == asset["source"]
        assert mine["stale"] is (not asset["is_realtime"])
        assert mine["assetClass"] == asset["asset_type"]
