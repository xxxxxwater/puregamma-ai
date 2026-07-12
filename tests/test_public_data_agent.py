from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from apps.api.config import Settings
from apps.api.services import agent_service
from packages.agents.llm.mock_provider import MockLLMProvider
from packages.data.binance_provider import BinanceProvider
from packages.data.defillama_provider import DefiLlamaProvider
from packages.data.onchain_provider import EVMRPCProvider
from packages.data.provider import DataSourceStatus
from packages.data.rss_provider import RSSProvider, RSSSource
from packages.database.models import AgentConversation, AgentMessage, AgentRun, MarketQuoteRecord, UsageEvent
from tests.conftest import auth_headers


def test_rss_real_parser_deduplicates_and_sanitizes(monkeypatch):
    source = RSSSource(id="coindesk", name="CoinDesk", url="https://www.coindesk.com/feed")
    feed = b'''<rss version="2.0"><channel><item><guid>1</guid><title>BTC rally</title><link>https://www.coindesk.com/a?utm_source=x</link><description><![CDATA[<script>alert(1)</script><b>Growth</b> update]]></description></item></channel></rss>'''
    provider = RSSProvider(sources=[source])
    monkeypatch.setattr(provider, "_fetch", lambda item: feed)

    result = provider.sync()

    assert result.status == DataSourceStatus.HEALTHY
    assert result.records[0]["canonical_url"] == "https://www.coindesk.com/a"
    assert "script" not in (result.records[0]["summary"] or "").lower()
    assert result.records[0]["sentiment_label"] == "positive"
    assert result.records[0]["provenance_json"]["isMock"] is False


def test_binance_sync_uses_decimal_and_partial_symbol_failure(monkeypatch):
    provider = BinanceProvider()
    monkeypatch.setattr(provider, "_get_json", lambda path, params=None: {"lastPrice": "100.123456789", "priceChangePercent": "1.2", "volume": "2.5", "quoteVolume": "250.30", "highPrice": "101", "lowPrice": "98", "bidPrice": "100", "askPrice": "100.2", "closeTime": 1783641600000})

    result = provider.sync(["BTC", "MISSING"])

    assert result.status == DataSourceStatus.PARTIAL
    assert result.records[0]["price"] == Decimal("100.123456789")
    assert result.records[0]["volume_24h_base"] == Decimal("2.5")
    assert result.records[0]["volume_24h_quote"] == Decimal("250.30")


class FakeDefiClient:
    def request_json(self, method, url):
        if url.endswith("/protocols"):
            return [{"id": "aave", "slug": "aave", "name": "Aave", "chain": "Ethereum", "tvl": 123.45}]
        if url.endswith("/v2/chains"):
            return [{"name": "Ethereum", "tvl": 456.78}]
        if url.endswith("/stablecoins"):
            return {"peggedAssets": []}
        if url.endswith("/overview/dexs") or url.endswith("/overview/fees"):
            return {"protocols": []}
        if url.endswith("/pools"):
            return {"data": []}
        raise AssertionError(url)


def test_defillama_free_succeeds_without_pro_key():
    result = DefiLlamaProvider(client=FakeDefiClient()).sync()
    assert result.status == DataSourceStatus.HEALTHY
    assert {row["entity_type"] for row in result.records} == {"protocol", "chain"}
    assert all(row["provider"] == "defillama" for row in result.records)


def test_evm_rpc_health_and_snapshot(monkeypatch):
    provider = EVMRPCProvider({"ethereum": "https://ethereum.example.com"})
    monkeypatch.setattr(provider, "chain_id", lambda chain: 1)
    monkeypatch.setattr(provider, "latest_block", lambda chain: (12345, datetime(2026, 7, 10, tzinfo=timezone.utc)))

    result = provider.sync()

    assert result.status == DataSourceStatus.HEALTHY
    assert {row["metric_type"] for row in result.records} == {"chain_id", "latest_block"}


def test_agent_conversation_stream_persists_usage(api_client, db, normal_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: Settings(enable_mock_agent=True, llm_provider="mock", agent_model="mock-model"))
    monkeypatch.setattr(agent_service, "get_llm_provider", lambda: MockLLMProvider())
    db.add(MarketQuoteRecord(symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", asset_type="spot", provider="binance", price=Decimal("100000"), change_24h_pct=Decimal("1.5"), volume_24h_base=Decimal("10"), volume_24h_quote=Decimal("1000000"), source_timestamp=datetime.now(timezone.utc), fetched_at=datetime.now(timezone.utc), provenance_json={"sourceUrl": "https://api.binance.com/api/v3/ticker/24hr", "isMock": False}))
    db.commit()
    created = api_client.post("/api/agent/conversations", json={"title": "BTC research"}, headers=auth_headers(normal_user))
    conversation_id = created.json()["conversation"]["id"]

    response = api_client.post(f"/api/agent/conversations/{conversation_id}/messages", json={"content": "What is the BTC market price?", "locale": "en"}, headers=auth_headers(normal_user))

    assert response.status_code == 200
    assert "event: run.started" in response.text
    assert "event: message.delta" in response.text
    assert "event: message.completed" in response.text
    run = db.query(AgentRun).filter_by(conversation_id=conversation_id).one()
    assistant = db.query(AgentMessage).filter_by(id=run.assistant_message_id).one()
    assert run.status == "completed"
    assert assistant.status == "completed"
    assert "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content." in assistant.content
    assert db.query(UsageEvent).filter_by(idempotency_key=f"agent-run:{run.id}").count() == 1


def test_agent_conversation_is_tenant_isolated(api_client, db, normal_user, pro_user):
    conversation = AgentConversation(user_id=normal_user.id, title="private")
    db.add(conversation)
    db.commit()

    response = api_client.get(f"/api/agent/conversations/{conversation.id}", headers=auth_headers(pro_user))

    assert response.status_code == 404


def test_agent_requires_authentication(api_client):
    response = api_client.post("/api/agent/conversations", json={"title": "no auth"})
    assert response.status_code == 401
