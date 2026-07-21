from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.services.billing_service import mock_upgrade
from apps.api.services.report_service import create_daily_report
from apps.api.services.signal_service import scan_signals
from packages.backtest.engine import BacktestEngine
from packages.data.binance_provider import BinanceProvider
from packages.data.base import MarketQuote, asset_type_for, is_equity
from packages.data.coinbase_provider import CoinbaseProvider
from packages.data.equity_providers.equity_provider import EquityDataProvider, equity_source_label
from packages.data.equity_providers.nasdaq_provider import NasdaqDataLinkProvider
from packages.data.mock_provider import MockMarketDataProvider
from packages.data.public_market_provider import PublicMarketDataProvider
from packages.risk.scoring import risk_score_for_quote
from packages.strategies.registry import generate_playbooks


def test_mock_market_provider():
    quotes = MockMarketDataProvider().get_snapshot(["BTC", "ETH", "SOL", "HYPE"])
    assert len(quotes) == 4
    assert quotes[0].price > 0


def test_mock_provider_equity_asset_types():
    quotes = MockMarketDataProvider().get_snapshot(["MSTR", "STRC"])
    assert quotes[0].symbol == "MSTR"
    assert quotes[0].asset_type == "equity"
    assert quotes[0].open_interest_usd is None
    assert quotes[0].funding_rate == 0.0
    assert quotes[1].symbol == "STRC"
    assert quotes[1].asset_type == "preferred_equity"
    assert quotes[1].open_interest_usd is None


def test_asset_type_for():
    assert asset_type_for("MSTR") == "equity"
    assert asset_type_for("STRC") == "preferred_equity"
    assert asset_type_for("STRD") == "preferred_equity"
    assert asset_type_for("STRK") == "preferred_equity"
    assert asset_type_for("STRF") == "preferred_equity"
    assert asset_type_for("BTC") == "crypto"
    assert asset_type_for("ETH") == "crypto"


def test_is_equity():
    assert is_equity("MSTR") is True
    assert is_equity("STRC") is True
    assert is_equity("BTC") is False


def test_equity_source_labels():
    assert equity_source_label("MSTR", "nasdaq") == "Nasdaq Data Link"
    assert equity_source_label("MSTR", "massive") == "Massive"
    assert equity_source_label("MSTR", "fmp") == "Financial Modeling Prep"
    assert equity_source_label("MSTR", "mock") == "MOCK"
    assert equity_source_label("STRC", "nasdaq") == "Nasdaq Data Link"
    assert equity_source_label("STRC", "massive") == "Massive"
    assert equity_source_label("STRC", "fmp") == "Financial Modeling Prep"
    assert equity_source_label("STRC", "mock") == "MOCK"


def test_nasdaq_data_link_snapshot_parsing():
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [{"symbol": "MSTR", "timestamp": "2026-07-10T15:30:01.000", "lastSale": 410.25, "volume": 1000, "percentChange": 1.75}]

    class Session:
        def post(self, *args, **kwargs):
            class TokenResponse(Response):
                def json(self):
                    return {"access_token": "token", "expires_in": 3600}

            return TokenResponse()

        def get(self, *args, **kwargs):
            assert kwargs["headers"]["Authorization"] == "Bearer token"
            return Response()

    provider = NasdaqDataLinkProvider("https://licensed.example", "client", "secret")
    provider._session = Session()
    quote = provider.get_quote("MSTR")
    assert quote is not None
    assert quote.price == 410.25
    assert quote.volume_24h == 410250
    assert quote.source == "nasdaq"
    assert quote.source_symbol == "NASDAQ:MSTR"
    assert quote.is_realtime is False


def test_public_market_provider_prefers_binance_before_coinbase():
    fallback = MockMarketDataProvider()
    calls: list[str] = []

    class FakeBinance:
        provider_name = "binance"

        def get_quote(self, symbol: str) -> MarketQuote:
            calls.append(f"binance:{symbol}")
            quote = fallback.get_snapshot([symbol])[0]
            return MarketQuote(
                **{
                    **quote.__dict__,
                    "price": 123.45,
                    "source": "binance",
                    "source_symbol": f"{symbol}USDT",
                    "is_realtime": True,
                    "change_24h": 1.23,
                }
            )

    class FakeCoinbase:
        provider_name = "coinbase"

        def get_quote(self, symbol: str) -> MarketQuote:
            calls.append(f"coinbase:{symbol}")
            raise AssertionError("Coinbase should not be called after Binance succeeds")

    quotes = PublicMarketDataProvider(providers=[FakeBinance(), FakeCoinbase()], fallback_provider=fallback).get_snapshot(["BTC"])
    assert quotes[0].source == "binance"
    assert quotes[0].price == 123.45
    assert calls == ["binance:BTC"]


def test_public_market_provider_routes_equity_to_equity_providers(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test_key_massive")
    fallback = MockMarketDataProvider()

    class FakeMassive:
        provider_name = "massive"
        enabled = True

        def get_quote(self, symbol: str) -> MarketQuote | None:
            quote = fallback.get_snapshot([symbol])[0]
            return MarketQuote(
                **{
                    **quote.__dict__,
                    "price": 2000.0,
                    "source": "massive",
                    "source_symbol": f"NASDAQ:{symbol}",
                    "is_realtime": True,
                    "change_24h": 3.5,
                    "asset_type": "equity",
                    "open_interest_usd": None,
                    "funding_rate": 0.0,
                }
            )

    provider = PublicMarketDataProvider(fallback_provider=fallback)
    provider._equity_provider = EquityDataProvider()
    provider._equity_provider._providers = [FakeMassive()]

    quotes = provider.get_snapshot(["MSTR"])
    assert quotes[0].symbol == "MSTR"
    assert quotes[0].source == "massive"
    assert quotes[0].is_realtime is True
    assert quotes[0].asset_type == "equity"
    assert quotes[0].open_interest_usd is None


def test_mstr_quote_not_mock_from_real_provider(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test")
    fallback = MockMarketDataProvider()

    class FakeMassiveQuote:
        provider_name = "massive"
        enabled = True

        def get_quote(self, symbol: str) -> MarketQuote | None:
            return MarketQuote(
                symbol=symbol,
                price=1950.0,
                volume_24h=2_500_000_000,
                market_cap=50_000_000_000,
                funding_rate=0.0,
                open_interest=0.0,
                volatility=0.55,
                liquidation_estimate=0.0,
                sentiment_score=0.6,
                timestamp=fallback.get_snapshot([symbol])[0].timestamp,
                source="massive",
                source_symbol=f"NASDAQ:{symbol}",
                change_24h=2.8,
                is_realtime=True,
                asset_type="equity",
                open_interest_usd=None,
            )

    provider = PublicMarketDataProvider(fallback_provider=fallback)
    provider._equity_provider = EquityDataProvider()
    provider._equity_provider._providers = [FakeMassiveQuote()]

    quotes = provider.get_snapshot(["MSTR"])
    assert quotes[0].source == "massive"
    assert quotes[0].is_realtime is True
    assert quotes[0].source != "mock"


def test_strc_quote_not_mock_from_real_provider(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test")
    fallback = MockMarketDataProvider()

    class FakeMassiveQuote:
        provider_name = "massive"
        enabled = True

        def get_quote(self, symbol: str) -> MarketQuote | None:
            return MarketQuote(
                symbol=symbol,
                price=105.0,
                volume_24h=150_000_000,
                market_cap=8_000_000_000,
                funding_rate=0.0,
                open_interest=0.0,
                volatility=0.3,
                liquidation_estimate=0.0,
                sentiment_score=0.5,
                timestamp=fallback.get_snapshot([symbol])[0].timestamp,
                source="massive",
                source_symbol=f"NASDAQ Preferred:{symbol}",
                change_24h=1.2,
                is_realtime=True,
                asset_type="preferred_equity",
                open_interest_usd=None,
            )

    provider = PublicMarketDataProvider(fallback_provider=fallback)
    provider._equity_provider = EquityDataProvider()
    provider._equity_provider._providers = [FakeMassiveQuote()]

    quotes = provider.get_snapshot(["STRC"])
    assert quotes[0].source == "massive"
    assert quotes[0].is_realtime is True
    assert quotes[0].source != "mock"


def test_api_failure_with_fallback_success(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_fmp")
    fallback = MockMarketDataProvider()

    class FailingMassive:
        provider_name = "massive"
        enabled = True

        def get_quote(self, symbol: str) -> MarketQuote | None:
            raise ValueError("Massive unavailable")

    class WorkingFMP:
        provider_name = "fmp"
        enabled = True

        def get_quote(self, symbol: str) -> MarketQuote | None:
            return MarketQuote(
                symbol=symbol,
                price=1900.0,
                volume_24h=2_000_000_000,
                market_cap=49_000_000_000,
                funding_rate=0.0,
                open_interest=0.0,
                volatility=0.5,
                liquidation_estimate=0.0,
                sentiment_score=0.55,
                timestamp=fallback.get_snapshot([symbol])[0].timestamp,
                source="fmp",
                source_symbol=f"NASDAQ:{symbol}",
                change_24h=2.5,
                is_realtime=True,
                asset_type="equity",
                open_interest_usd=None,
            )

    provider = PublicMarketDataProvider(fallback_provider=fallback)
    provider._equity_provider = EquityDataProvider()
    provider._equity_provider._providers = [FailingMassive(), WorkingFMP()]

    quotes = provider.get_snapshot(["MSTR"])
    assert quotes[0].source == "fmp"


def test_all_providers_fail_no_mock_raises(monkeypatch):
    monkeypatch.setenv("ENABLE_MOCK_MARKET_DATA", "false")

    class FailingProvider:
        provider_name = "massive"
        enabled = True

        def get_quote(self, symbol: str) -> MarketQuote | None:
            raise ValueError("Down")

    eq = EquityDataProvider()
    eq._providers = [FailingProvider(), FailingProvider(), FailingProvider()]

    try:
        eq.get_quote("MSTR")
        assert False, "Should have raised RuntimeError"
    except RuntimeError as exc:
        assert "ENABLE_MOCK_MARKET_DATA=true" in str(exc)


def test_all_providers_fail_mock_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_MOCK_MARKET_DATA", "true")

    class FailingProvider:
        provider_name = "massive"
        enabled = True

        def get_quote(self, symbol: str) -> MarketQuote | None:
            raise ValueError("Down")

    eq = EquityDataProvider()
    eq._providers = [FailingProvider(), FailingProvider(), FailingProvider()]

    quote = eq.get_quote("MSTR")
    assert quote.source == "mock"
    assert quote.is_realtime is False
    assert quote.asset_type == "equity"
    assert quote.open_interest_usd is None


def test_binance_provider_parses_public_24hr_ticker_payload():
    quote = BinanceProvider()._quote_from_payload(
        "BTC",
        "BTCUSDT",
        {"lastPrice": "62842.76", "quoteVolume": "44100000000.5", "priceChangePercent": "0.479", "closeTime": "1783579500000"},
    )
    assert quote.symbol == "BTC"
    assert quote.price == 62842.76
    assert quote.volume_24h == 44100000000.5
    assert quote.change_24h == 0.479
    assert quote.source == "binance"
    assert quote.is_realtime is True


def test_coinbase_provider_parses_public_ticker_and_stats_payload():
    quote = CoinbaseProvider()._quote_from_payload(
        "ETH",
        "ETH-USD",
        {"price": "3500", "volume": "1200", "time": "2026-07-09T06:45:03.214385621Z"},
        {"open": "3400", "last": "3500", "volume": "2000"},
    )
    assert quote.symbol == "ETH"
    assert quote.price == 3500
    assert quote.volume_24h == 7_000_000
    assert round(quote.change_24h or 0, 4) == 2.9412
    assert quote.source == "coinbase"
    assert quote.is_realtime is True


def test_daily_report_generation(db, demo_user):
    report = create_daily_report(db, demo_user.id)
    assert report.content_markdown.strip()
    assert "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content." in report.content_markdown


def test_signal_scan(db):
    signals = scan_signals(db, ["BTC", "ETH"])
    assert len(signals) == 2
    assert signals[0].thesis


def test_risk_score():
    quote = MockMarketDataProvider().get_snapshot(["HYPE"])[0]
    assert 0 <= risk_score_for_quote(quote) <= 100


def test_strategy_output():
    playbooks = generate_playbooks()
    assert len(playbooks) == 6
    assert playbooks[0]["strategy_name"] == "BTC momentum breakout"


def test_backtest_metrics(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    result = BacktestEngine().run("BTC momentum breakout", "BTC")
    assert "metrics" in result
    assert "max_drawdown" in result["metrics"]


def test_api_health_check():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_market_snapshot_api_includes_equity_fields(monkeypatch):
    monkeypatch.setenv("ENABLE_MOCK_MARKET_DATA", "true")
    client = TestClient(app)
    response = client.get("/market/snapshot")
    assert response.status_code == 200
    data = response.json()
    mstr = next((a for a in data["assets"] if a["symbol"] == "MSTR"), None)
    strc = next((a for a in data["assets"] if a["symbol"] == "STRC"), None)
    assert mstr is not None
    assert strc is not None
    assert mstr["asset_type"] == "equity"
    assert strc["asset_type"] == "preferred_equity"
    assert mstr["open_interest"] is None
    assert strc["open_interest"] is None
    assert "source_display" in mstr
    assert "source_display" in strc
