from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session

from packages.database.models import DataSource, DefiMetric, MarketQuoteRecord, NewsItem, NormalizedDocument, OnchainMetric


@dataclass
class ToolSource:
    provider: str
    title: str
    url: str | None
    published_at: datetime | None
    source_timestamp: datetime | None
    fetched_at: datetime


@dataclass
class ToolResult:
    tool_name: str
    data: Any
    summary: str
    sources: list[ToolSource] = field(default_factory=list)


def _provenance_url(row: Any) -> str | None:
    value = getattr(row, "provenance_json", {}) or {}
    return value.get("sourceUrl")


class AgentToolRegistry:
    """Read-only, fixed tool allowlist backed by synchronized database records."""

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        self.tools: dict[str, Callable[..., ToolResult]] = {
            "get_market_quote": self.get_market_quote,
            "get_market_history": self.get_market_history,
            "get_recent_news": self.get_recent_news,
            "search_news": self.search_news,
            "search_source_documents": self.search_source_documents,
            "get_defi_protocol_metrics": self.get_defi_protocol_metrics,
            "get_chain_metrics": self.get_chain_metrics,
            "get_onchain_snapshot": self.get_chain_metrics,
            "get_data_source_status": self.get_data_source_status,
            # ── NautilusTrader strategy research tools ──
            "run_nautilus_backtest": self.run_nautilus_backtest,
            "list_research_strategies": self.list_research_strategies,
            "get_strategy_performance": self.get_strategy_performance,
        }

    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in self.tools:
            raise ValueError(f"Tool is not allowlisted: {name}")
        return self.tools[name](**arguments)

    def plan(self, query: str) -> list[tuple[str, dict[str, Any]]]:
        lowered = query.lower()
        symbols = [symbol for symbol in ("BTC", "ETH", "SOL", "HYPE", "MSTR", "STRC") if re.search(rf"\b{symbol}\b", query, re.I)]
        calls: list[tuple[str, dict[str, Any]]] = []
        if symbols or any(word in lowered for word in ("price", "market", "quote", "行情", "价格", "市场")):
            calls.append(("get_market_quote", {"symbols": symbols or ["BTC", "ETH"]}))
        if any(word in lowered for word in ("news", "headline", "catalyst", "sentiment", "fintwit", "twitter", "bloomberg", "观点", "情绪", "新闻", "消息", "催化", "来源")):
            providers = [provider for provider in ("rss", "fintwit", "x-twitter", "bloomberg") if provider.split("-")[0] in lowered]
            calls.append(("search_source_documents", {"query": query, "symbols": symbols, "providers": providers, "hours": 72}))
        if any(word in lowered for word in ("defi", "tvl", "apy", "yield", "fees", "revenue", "协议", "收益率")):
            calls.append(("get_defi_protocol_metrics", {"query": query}))
        if any(word in lowered for word in ("onchain", "chain", "block", "rpc", "链上", "区块")):
            calls.append(("get_chain_metrics", {}))
        if any(word in lowered for word in ("source", "freshness", "provider", "数据源", "新鲜度")):
            calls.append(("get_data_source_status", {}))
        # ── NautilusTrader strategy research ──
        if any(word in lowered for word in ("backtest", "回测", "strategy", "策略", "performance", "绩效", "sharpe", "drawdown")):
            calls.append(("list_research_strategies", {}))
            if symbols:
                calls.append(("run_nautilus_backtest", {"symbols": symbols[:2], "lookback_days": 90}))
        return calls[:6]

    def get_market_quote(self, symbols: list[str]) -> ToolResult:
        rows = []
        sources = []
        for symbol in symbols[:12]:
            row = self.db.query(MarketQuoteRecord).filter(MarketQuoteRecord.base_asset == symbol.upper()).order_by(MarketQuoteRecord.fetched_at.desc()).first()
            if not row:
                continue
            age = (datetime.now(timezone.utc) - _aware(row.fetched_at)).total_seconds()
            rows.append({"symbol": row.base_asset, "pair": row.symbol, "price": _string(row.price), "change24hPct": _string(row.change_24h_pct), "volume24hBase": _string(row.volume_24h_base), "volume24hQuote": _string(row.volume_24h_quote), "provider": row.provider, "sourceTimestamp": _iso(row.source_timestamp), "fetchedAt": _iso(row.fetched_at), "fresh": age <= 300})
            sources.append(ToolSource(row.provider, f"{row.symbol} 24h ticker", _provenance_url(row), None, row.source_timestamp, row.fetched_at))
        summary = f"Retrieved {len(rows)} persisted market quotes" if rows else "No synchronized market quote is available"
        return ToolResult("get_market_quote", rows, summary, sources)

    def get_market_history(self, symbol: str, limit: int = 50) -> ToolResult:
        rows = self.db.query(MarketQuoteRecord).filter(MarketQuoteRecord.base_asset == symbol.upper()).order_by(MarketQuoteRecord.fetched_at.desc()).limit(min(limit, 100)).all()
        data = [{"price": _string(row.price), "sourceTimestamp": _iso(row.source_timestamp), "fetchedAt": _iso(row.fetched_at), "provider": row.provider} for row in rows]
        sources = [ToolSource(row.provider, f"{row.symbol} quote history", _provenance_url(row), None, row.source_timestamp, row.fetched_at) for row in rows[:5]]
        return ToolResult("get_market_history", data, f"Retrieved {len(data)} quote observations", sources)

    def get_recent_news(self, hours: int = 48, symbols: list[str] | None = None) -> ToolResult:
        return self.search_news(query="", symbols=symbols or [], hours=hours)

    def search_news(self, query: str, symbols: list[str] | None = None, hours: int = 72) -> ToolResult:
        unified = self.search_source_documents(query=query, symbols=symbols, providers=["rss", "bloomberg"], hours=hours)
        if unified.data:
            return ToolResult("search_news", unified.data, unified.summary, unified.sources)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=min(max(hours, 1), 720))
        q = self.db.query(NewsItem).filter(NewsItem.fetched_at >= cutoff)
        words = [word.lower() for word in re.findall(r"[A-Za-z]{4,}", query) if word.lower() not in {"what", "with", "from", "market", "about"}][:5]
        rows = q.order_by(NewsItem.published_at.desc(), NewsItem.fetched_at.desc()).limit(100).all()
        filtered = []
        for row in rows:
            haystack = f"{row.title} {row.summary or ''}".lower()
            symbol_match = not symbols or any(symbol.upper() in (row.related_symbols or []) for symbol in symbols)
            word_match = not words or any(word in haystack for word in words)
            if symbol_match and word_match:
                filtered.append(row)
            if len(filtered) >= 12:
                break
        data = [{"source": row.source, "title": row.title, "summary": row.summary, "url": row.url, "publishedAt": _iso(row.published_at), "fetchedAt": _iso(row.fetched_at), "sentiment": row.sentiment_label, "symbols": row.related_symbols} for row in filtered]
        sources = [ToolSource("rss", row.title, row.url, row.published_at, row.published_at, row.fetched_at) for row in filtered]
        return ToolResult("search_news", data, f"Retrieved {len(data)} synchronized RSS items" if data else "No matching synchronized RSS news is available", sources)

    def search_source_documents(self, query: str = "", symbols: list[str] | None = None, providers: list[str] | None = None, topics: list[str] | None = None, authors: list[str] | None = None, hours: int = 72) -> ToolResult:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=min(max(hours, 1), 720))
        q = self.db.query(NormalizedDocument).filter(NormalizedDocument.created_at >= cutoff)
        if providers:
            q = q.filter(NormalizedDocument.provider.in_(providers[:10]))
        rows = q.order_by(NormalizedDocument.published_at.desc(), NormalizedDocument.created_at.desc()).limit(300).all()
        words = [word.lower() for word in re.findall(r"[A-Za-z]{4,}", query) if word.lower() not in {"what", "with", "from", "market", "about", "which", "recent"}][:8]
        selected = []
        for row in rows:
            haystack = f"{row.title} {row.summary} {row.content}".lower()
            if symbols and not any(symbol.upper() in (row.symbols or []) for symbol in symbols):
                continue
            if topics and not any(topic.lower() in {item.lower() for item in (row.topics or [])} for topic in topics):
                continue
            if authors and (row.author or "").lower() not in {item.lower().lstrip("@") for item in authors}:
                continue
            if words and not any(word in haystack for word in words):
                continue
            selected.append(row)
            if len(selected) >= 20:
                break
        data = [{"provider": row.provider, "sourceType": row.source_type, "evidenceType": "source_opinion" if "opinion" in row.source_type else "reported_fact", "source": row.source_name, "author": row.author, "title": row.title, "summary": row.summary, "url": row.url, "publishedAt": _iso(row.published_at), "fetchedAt": _iso(row.created_at), "symbols": row.symbols, "topics": row.topics, "sentiment": row.sentiment, "credibilityScore": row.credibility_score, "weightedScore": row.final_score, "eventFingerprint": row.event_fingerprint, "licenseStatus": row.license_status} for row in selected]
        sources = [ToolSource(row.provider, row.title, row.url, row.published_at, row.published_at, row.created_at) for row in selected]
        summary = f"Retrieved {len(selected)} traceable documents from {len({row.provider for row in selected})} providers" if selected else "Connected sources do not contain enough matching evidence"
        return ToolResult("search_source_documents", data, summary, sources)

    def get_defi_protocol_metrics(self, query: str = "") -> ToolResult:
        rows = self.db.query(DefiMetric).order_by(DefiMetric.fetched_at.desc()).limit(200).all()
        words = [word.lower() for word in re.findall(r"[A-Za-z0-9-]{3,}", query)][:10]
        selected = [row for row in rows if not words or any(word in f"{row.entity_name} {row.chain or ''} {row.metric_type}".lower() for word in words)][:20]
        if not selected:
            selected = rows[:12]
        data = [{"entity": row.entity_name, "entityType": row.entity_type, "chain": row.chain, "metric": row.metric_type, "value": _string(row.value), "currency": row.currency, "fetchedAt": _iso(row.fetched_at)} for row in selected]
        sources = [ToolSource("defillama", f"{row.entity_name} {row.metric_type}", _provenance_url(row), None, row.source_timestamp, row.fetched_at) for row in selected[:10]]
        return ToolResult("get_defi_protocol_metrics", data, f"Retrieved {len(data)} DefiLlama metrics" if data else "No synchronized DefiLlama metrics are available", sources)

    def get_chain_metrics(self) -> ToolResult:
        rows = self.db.query(OnchainMetric).order_by(OnchainMetric.fetched_at.desc()).limit(50).all()
        data = [{"provider": row.provider, "chain": row.chain, "entity": row.entity_id, "metric": row.metric_type, "value": row.value, "blockNumber": row.block_number, "sourceTimestamp": _iso(row.source_timestamp), "fetchedAt": _iso(row.fetched_at)} for row in rows]
        sources = [ToolSource(row.provider, f"{row.chain} {row.metric_type}", _provenance_url(row), None, row.source_timestamp, row.fetched_at) for row in rows[:10]]
        return ToolResult("get_chain_metrics", data, f"Retrieved {len(data)} on-chain metrics" if data else "No synchronized on-chain metrics are available", sources)

    def get_data_source_status(self) -> ToolResult:
        rows = self.db.query(DataSource).order_by(DataSource.name).all()
        data = [{"id": row.id, "name": row.name, "status": row.status, "lastSuccessAt": _iso(row.last_success_at), "items": row.item_count, "error": row.last_error} for row in rows]
        return ToolResult("get_data_source_status", data, f"Retrieved status for {len(data)} data sources")

    # ── NautilusTrader strategy research tools ──

    def run_nautilus_backtest(self, symbols: list[str], lookback_days: int = 90) -> ToolResult:
        """Run NautilusTrader backtest using PureGamma data catalog."""
        from packages.backtest.engine import run_backtest_for_agent
        results = []
        sources: list[ToolSource] = []
        for symbol in symbols[:3]:
            result = run_backtest_for_agent(
                self.db,
                strategy_name=f"{symbol} momentum breakout",
                asset=symbol,
                params={"lookback_days": lookback_days},
            )
            results.append(result)
            sources.append(ToolSource(
                "nautilus_trader",
                f"{symbol} backtest ({result.get('engine', 'unknown')})",
                None,
                None,
                None,
                datetime.now(timezone.utc),
            ))
        summary = f"Ran NautilusTrader backtests for {len(results)} assets" if results else "No backtest results available"
        return ToolResult("run_nautilus_backtest", results, summary, sources)

    def list_research_strategies(self) -> ToolResult:
        """List available NautilusTrader research strategies with metadata."""
        from packages.strategies.registry import generate_playbooks
        playbooks = generate_playbooks()
        data = [
            {
                "name": pb["strategy_name"],
                "asset": pb["asset"],
                "thesis": pb["thesis"],
                "trigger": pb["trigger"],
                "timeframe": pb["timeframe"],
                "risk_score": pb["risk_score"],
                "confidence": pb["confidence"],
                "required_data_sources": pb["required_data_sources"],
            }
            for pb in playbooks
        ]
        summary = f"Available NautilusTrader strategies: {len(data)} research playbooks"
        return ToolResult("list_research_strategies", data, summary)

    def get_strategy_performance(self, strategy_name: str, asset: str) -> ToolResult:
        """Get detailed performance metrics for a specific strategy via NautilusTrader."""
        from packages.backtest.engine import run_backtest_for_agent
        result = run_backtest_for_agent(
            self.db,
            strategy_name=strategy_name,
            asset=asset,
            params={"lookback_days": 90},
        )
        sources = [ToolSource(
            result.get("engine", "nautilus_trader"),
            f"{strategy_name} on {asset}",
            None,
            None,
            None,
            datetime.now(timezone.utc),
        )]
        return ToolResult(
            "get_strategy_performance",
            result,
            f"Strategy: {strategy_name} | Return: {result.get('total_return', 0):.2%} | Sharpe: {result.get('sharpe_ratio', 0):.2f} | Max DD: {result.get('max_drawdown', 0):.2%} | Engine: {result.get('engine', 'unknown')}",
            sources,
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None


def _string(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None
