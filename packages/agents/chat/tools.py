from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import (
    AccountSnapshot,
    DataSource,
    DefiMetric,
    MarketQuoteRecord,
    NewsItem,
    NormalizedDocument,
    OnchainMetric,
    OrderJournal,
    PositionSnapshot,
    StrategyIntent,
    TradingAccount,
    TradingStrategy,
)


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
    """Fixed tool allowlist. Trading writes delegate to the audited control plane."""

    def __init__(self, db: Session, user_id: str, conversation_id: str | None = None):
        from apps.api.services.entitlement_service import get_user_entitlement

        self.db = db
        self.user_id = user_id
        self.conversation_id = conversation_id
        entitlement = get_user_entitlement(db, user_id)
        self.allowed_data_sources = set(entitlement["allowed_data_sources"])
        if "all" in self.allowed_data_sources:
            self.allowed_data_sources = {"market", "rss", "fintwit", "x", "x-twitter", "bloomberg", "portfolio", "options", "onchain", "defillama"}
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
            "get_sentiment_context": self.get_sentiment_context,
            "get_account_snapshot": self.get_account_snapshot,
            "get_position_snapshot": self.get_position_snapshot,
            "get_open_orders": self.get_open_orders,
            "get_strategy_status": self.get_strategy_status,
            "get_options_context": self.get_options_context,
            "get_earnings_gamma": self.get_earnings_gamma,
            "create_strategy_draft": self.create_strategy_draft,
            "modify_strategy_draft": self.modify_strategy_draft,
            "validate_strategy": self.validate_strategy_tool,
            "backtest_strategy": self.backtest_strategy,
            "create_paper_run": self.create_paper_run,
            "create_shadow_run": self.create_shadow_run,
            "preview_strategy_activation": self.preview_strategy_activation,
            "activate_strategy": self.activate_strategy_tool,
            "pause_strategy": self.pause_strategy,
            "resume_strategy": self.resume_strategy,
            "stop_strategy": self.stop_strategy,
            "reconcile_account": self.reconcile_account_tool,
            "generate_order_preview": self.generate_order_preview,
        }

    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in self.tools:
            raise ValueError(f"Tool is not allowlisted: {name}")
        required_source = {
            "get_market_quote": "market",
            "get_market_history": "market",
            "get_defi_protocol_metrics": "onchain",
            "get_chain_metrics": "onchain",
            "get_onchain_snapshot": "onchain",
            "get_account_snapshot": "portfolio",
            "get_position_snapshot": "portfolio",
            "get_open_orders": "portfolio",
            "get_options_context": "options",
        }.get(name)
        if required_source and required_source not in self.allowed_data_sources:
            raise PermissionError("TOOL_ENTITLEMENT_DENIED")
        return self.tools[name](**arguments)

    def plan(self, query: str, skills: list[str] | None = None, data_sources: list[str] | None = None, skill_tool_allowlist: set[str] | None = None) -> list[tuple[str, dict[str, Any]]]:
        lowered = query.lower()
        symbols = [
            symbol
            for symbol in ("BTC", "ETH", "HYPE", "MSTR", "STRC")
            if re.search(rf"\b{symbol}\b", query, re.I)
        ]
        calls: list[tuple[str, dict[str, Any]]] = []
        selected_sources = set(data_sources or [])
        confirmation = query.strip()
        if confirmation.startswith("CONFIRM STRATEGY "):
            return [("activate_strategy", {"confirmation": confirmation})]
        strategy_words = any(word in lowered for word in ("strategy", "策略"))
        if strategy_words and any(
            word in lowered
            for word in ("create", "design", "draft", "创建", "设计", "生成")
        ):
            return [
                (
                    "create_strategy_draft",
                    {"request": query, "symbols": symbols or ["BTC"]},
                )
            ]
        if strategy_words and any(
            word in lowered for word in ("start", "activate", "启动", "激活")
        ):
            mode = (
                "SHADOW"
                if any(word in lowered for word in ("shadow", "影子"))
                else "PAPER"
            )
            return [("preview_strategy_activation", {"mode": mode})]
        if strategy_words and any(word in lowered for word in ("backtest", "回测")):
            engine = "nautilus" if "nautilus" in lowered else "mock"
            return [("backtest_strategy", {"engine": engine})]
        if strategy_words and any(word in lowered for word in ("pause", "暂停")):
            return [("pause_strategy", {})]
        if strategy_words and any(word in lowered for word in ("resume", "恢复")):
            return [("resume_strategy", {})]
        if strategy_words and any(word in lowered for word in ("stop", "停止")):
            return [("stop_strategy", {})]
        if strategy_words and any(
            word in lowered
            for word in ("status", "状态", "position", "仓位", "order", "订单")
        ):
            calls.append(("get_strategy_status", {}))
        if any(
            word in lowered
            for word in (
                "buy",
                "sell",
                "long",
                "short",
                "买",
                "卖",
                "做多",
                "做空",
                "平仓",
            )
        ):
            return [("generate_order_preview", {"request": query, "symbols": symbols})]
        if symbols or any(
            word in lowered
            for word in ("price", "market", "quote", "行情", "价格", "市场")
        ):
            calls.append(("get_market_quote", {"symbols": symbols or ["BTC", "ETH"]}))
        if any(
            word in lowered
            for word in ("news", "headline", "rss", "bloomberg", "新闻", "消息", "来源")
        ):
            providers = [provider for provider in ("rss", "fintwit", "x-twitter", "bloomberg") if provider in selected_sources and self._provider_allowed(provider)]
            calls.append(
                (
                    "search_source_documents",
                    {
                        "query": query,
                        "symbols": symbols,
                        "providers": providers,
                        "hours": 72,
                    },
                )
            )
        if any(
            word in lowered
            for word in (
                "defi",
                "tvl",
                "apy",
                "yield",
                "fees",
                "revenue",
                "协议",
                "收益率",
            )
        ):
            calls.append(("get_defi_protocol_metrics", {"query": query}))
        if any(
            word in lowered
            for word in ("onchain", "chain", "block", "rpc", "链上", "区块")
        ):
            calls.append(("get_chain_metrics", {}))
        if any(
            word in lowered
            for word in ("source", "freshness", "provider", "数据源", "新鲜度")
        ):
            calls.append(("get_data_source_status", {}))
        if any(
            word in lowered
            for word in (
                "option",
                "options",
                "deribit",
                "gamma",
                "theta",
                "vega",
                "implied volatility",
                "期权",
                "隐含波动率",
                "波动率曲面",
            )
            ):
                currency = "ETH" if "ETH" in symbols else "BTC"
                calls.append(("get_options_context", {"currency": currency}))
        if any(
            word in lowered
            for word in (
                "earnings",
                "财报",
                "美股",
                "stock gamma",
                "equity gamma",
                "us stock",
            )
        ):
            calls.append(("get_earnings_gamma", {"language": "en"}))
        if "market" in selected_sources and not any(name == "get_market_quote" for name, _ in calls):
            calls.append(("get_market_quote", {"symbols": symbols or ["BTC", "ETH"]}))
        selected_news = sorted(selected_sources.intersection({"rss", "fintwit", "x-twitter", "bloomberg"}))
        if selected_news and not any(name == "search_source_documents" for name, _ in calls):
            calls.append(("search_source_documents", {"query": query, "symbols": symbols, "providers": selected_news, "hours": 72}))
        if "portfolio" in selected_sources:
            if not any(name == "get_account_snapshot" for name, _ in calls):
                calls.append(("get_account_snapshot", {}))
            if not any(name == "get_position_snapshot" for name, _ in calls):
                calls.append(("get_position_snapshot", {}))
        if "options" in selected_sources and not any(name == "get_options_context" for name, _ in calls):
            calls.append(("get_options_context", {"currency": "ETH" if "ETH" in symbols else "BTC"}))
        skill_tools = {
            "market_research": {"get_market_quote", "get_market_history", "get_data_source_status"},
            "news_research": {"get_recent_news", "search_news", "search_source_documents", "get_sentiment_context"},
            "portfolio_review": {"get_account_snapshot", "get_position_snapshot", "get_open_orders"},
            "options_analysis": {"get_options_context", "get_earnings_gamma"},
            "source_check": {"get_data_source_status", "search_source_documents"},
            "deep_research": {"get_market_quote", "get_market_history", "search_source_documents", "get_defi_protocol_metrics", "get_chain_metrics", "get_data_source_status", "get_account_snapshot", "get_position_snapshot", "get_options_context", "list_research_strategies", "run_nautilus_backtest", "get_strategy_performance"},
        }
        allowed = skill_tool_allowlist if skill_tool_allowlist is not None else set().union(*(skill_tools.get(skill, set()) for skill in (skills or [])))
        restricted = skill_tool_allowlist is not None or bool(skills)
        return [call for call in calls if not restricted or call[0] in allowed][:6]

    def get_options_context(self, currency: str = "BTC") -> ToolResult:
        from apps.api.services.options_service import get_option_chain
        from packages.options.long_gamma import discover_long_gamma

        chain = get_option_chain(currency)
        if chain["status"] != "HEALTHY":
            raise ValueError(chain.get("error", "Deribit option data is unavailable"))
        candidates = discover_long_gamma(chain["instruments"], 8)
        fetched_at = datetime.fromisoformat(chain["fetched_at"])
        source = ToolSource(
            provider="deribit_public",
            title=f"Deribit {currency.upper()} public option chain",
            url=chain["source_url"],
            published_at=None,
            source_timestamp=fetched_at,
            fetched_at=fetched_at,
        )
        return ToolResult(
            "get_options_context",
            {
                "currency": currency.upper(),
                "candidateCount": len(candidates),
                "candidates": candidates,
                "liveTrading": False,
            },
            f"Retrieved {len(candidates)} read-only long gamma research candidates",
            [source],
        )

    def get_earnings_gamma(self, language: str = "en") -> ToolResult:
        from packages.options.earnings_gamma import get_earnings_candidates, refresh_earnings_candidates

        candidates = get_earnings_candidates(language)
        if not candidates:
            candidates = refresh_earnings_candidates(self.db, language)
        return ToolResult(
            "get_earnings_gamma",
            {
                "candidateCount": len(candidates),
                "candidates": candidates[:10],
                "source": "earnings_research",
                "liveTrading": False,
            },
            f"Retrieved {len(candidates)} US stock earnings gamma candidates",
            [],
        )

    def _latest_strategy(self) -> TradingStrategy:
        query = self.db.query(TradingStrategy).filter_by(user_id=self.user_id)
        if self.conversation_id:
            in_conversation = (
                query.filter_by(conversation_id=self.conversation_id)
                .order_by(TradingStrategy.updated_at.desc())
                .first()
            )
            if in_conversation:
                return in_conversation
        row = query.order_by(TradingStrategy.updated_at.desc()).first()
        if not row:
            raise ValueError("No strategy draft exists in this account")
        return row

    def get_sentiment_context(self, symbols: list[str], hours: int = 24) -> ToolResult:
        return self.search_source_documents(
            symbols=symbols,
            hours=hours,
            providers=["rss", "fintwit", "x-twitter", "bloomberg"],
        )

    def get_account_snapshot(self) -> ToolResult:
        rows = (
            self.db.query(TradingAccount)
            .filter_by(user_id=self.user_id)
            .order_by(TradingAccount.created_at)
            .all()
        )
        data = []
        for row in rows:
            snapshot = (
                self.db.query(AccountSnapshot)
                .filter_by(user_id=self.user_id, account_id=row.id)
                .order_by(AccountSnapshot.captured_at.desc())
                .first()
            )
            data.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "venue": row.venue,
                    "accountType": row.account_type,
                    "status": row.status,
                    "permissions": row.permissions_json,
                    "performance": {
                        "balance": snapshot.balance,
                        "equity": snapshot.equity,
                        "dailyPnl": snapshot.daily_pnl,
                        "drawdown": snapshot.drawdown,
                        "exposure": snapshot.exposure,
                        "capturedAt": _iso(snapshot.captured_at),
                    }
                    if snapshot
                    else None,
                }
            )
        return ToolResult(
            "get_account_snapshot",
            data,
            f"Retrieved {len(data)} tenant-owned trading accounts",
        )

    def get_position_snapshot(self) -> ToolResult:
        history = (
            self.db.query(PositionSnapshot)
            .filter_by(user_id=self.user_id)
            .order_by(PositionSnapshot.captured_at.desc())
            .limit(50)
            .all()
        )
        rows = []
        seen = set()
        for row in history:
            key = (row.account_id, row.instrument)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
        data = [
            {
                "accountId": row.account_id,
                "strategyId": row.strategy_id,
                "instrument": row.instrument,
                "quantity": row.quantity,
                "side": row.side,
                "markPrice": row.mark_price,
                "unrealizedPnl": row.unrealized_pnl,
                "capturedAt": _iso(row.captured_at),
            }
            for row in rows
        ]
        return ToolResult(
            "get_position_snapshot", data, f"Retrieved {len(data)} position snapshots"
        )

    def get_open_orders(self) -> ToolResult:
        rows = (
            self.db.query(OrderJournal)
            .filter(
                OrderJournal.user_id == self.user_id,
                OrderJournal.state.notin_(
                    ["FILLED", "CANCELED", "REJECTED", "EXPIRED"]
                ),
            )
            .order_by(OrderJournal.created_at.desc())
            .limit(50)
            .all()
        )
        data = [
            {
                "clientOrderId": row.client_order_id,
                "instrument": row.instrument,
                "side": row.side,
                "state": row.state,
                "quantity": row.quantity,
                "filledQuantity": row.filled_quantity,
                "remainingQuantity": row.remaining_quantity,
            }
            for row in rows
        ]
        return ToolResult(
            "get_open_orders", data, f"Retrieved {len(data)} open or uncertain orders"
        )

    def get_strategy_status(self) -> ToolResult:
        from apps.api.services.strategy_control_service import serialize_strategy

        strategy = self._latest_strategy()
        return ToolResult(
            "get_strategy_status",
            serialize_strategy(self.db, strategy),
            f"Strategy {strategy.name} is {strategy.status}",
        )

    def create_strategy_draft(self, request: str, symbols: list[str]) -> ToolResult:
        from apps.api.services.strategy_control_service import (
            create_strategy,
            serialize_strategy,
        )

        primary = symbols[0].upper()
        timeframe_match = re.search(
            r"\b(\d+)\s*(m|min|h|hour|小时|分钟|d|day)\b", request, re.I
        )
        timeframe = (
            f"{timeframe_match.group(1)}{timeframe_match.group(2).lower()}"
            if timeframe_match
            else "1h"
        )
        sources = [
            source
            for source, terms in {
                "rss": ("rss", "news", "新闻"),
                "fintwit": ("fintwit", "kol"),
                "x-twitter": ("twitter", " x ", "推特"),
                "bloomberg": ("bloomberg", "彭博"),
            }.items()
            if any(term in f" {request.lower()} " for term in terms)
        ]
        draft = {
            "name": f"{primary} {timeframe} Agent strategy",
            "description": request[:1000],
            "instruments": [f"{primary}USDT"],
            "venues": ["MOCK"],
            "timeframe": timeframe,
            "strategy_type": "trend",
            "entry_rules": [
                {"type": "momentum", "condition": "close_above_20_period_high"}
            ],
            "exit_rules": [{"type": "risk", "condition": "stop_or_take_profit"}],
            "filters": [],
            "feature_sources": ["market", *sources],
            "sentiment_sources": sources,
            "execution_mode": "PAPER",
        }
        strategy = create_strategy(
            self.db, self.user_id, draft, conversation_id=self.conversation_id
        )
        data = serialize_strategy(self.db, strategy)
        return ToolResult(
            "create_strategy_draft",
            data,
            f"Created strategy draft {strategy.name} version {strategy.current_version}; no runtime was started",
        )

    def modify_strategy_draft(self, changes: dict) -> ToolResult:
        from apps.api.services.strategy_control_service import (
            modify_strategy,
            serialize_strategy,
        )

        strategy = modify_strategy(
            self.db, self.user_id, self._latest_strategy().id, changes
        )
        return ToolResult(
            "modify_strategy_draft",
            serialize_strategy(self.db, strategy),
            f"Created immutable strategy version {strategy.current_version}",
        )

    def validate_strategy_tool(self) -> ToolResult:
        from apps.api.services.strategy_control_service import (
            serialize_strategy,
            validate_draft,
        )

        strategy = self._latest_strategy()
        result = validate_draft(serialize_strategy(self.db, strategy)["draft"])
        return ToolResult("validate_strategy", result, "Strategy validation completed")

    def backtest_strategy(self, engine: str = "mock") -> ToolResult:
        from apps.api.services.strategy_control_service import run_strategy_backtest
        from apps.api.routers.backtest import serialize_run

        strategy = self._latest_strategy()
        result = serialize_run(
            run_strategy_backtest(self.db, self.user_id, strategy.id, engine)
        )
        return ToolResult(
            "backtest_strategy",
            result,
            f"Completed {engine} backtest for strategy version {strategy.current_version}",
        )

    def create_paper_run(self) -> ToolResult:
        return self.preview_strategy_activation("PAPER")

    def create_shadow_run(self) -> ToolResult:
        return self.preview_strategy_activation("SHADOW")

    def preview_strategy_activation(self, mode: str = "PAPER") -> ToolResult:
        from apps.api.services.strategy_control_service import (
            preview_activation,
            serialize_intent,
        )

        strategy = self._latest_strategy()
        intent, confirmation = preview_activation(
            self.db,
            self.user_id,
            strategy.id,
            mode=mode,
            account_id=None,
            conversation_id=self.conversation_id,
        )
        return ToolResult(
            "preview_strategy_activation",
            serialize_intent(intent, confirmation),
            f"Prepared {mode} activation preview for version {strategy.current_version}. Runtime not started; exact confirmation is required in a new turn",
        )

    def activate_strategy_tool(self, confirmation: str) -> ToolResult:
        from apps.api.services.strategy_control_service import (
            activate_strategy,
            serialize_activation,
            serialize_run,
        )
        from packages.trading.policies.safety import confirmation_hash
        import secrets

        pending = (
            self.db.query(StrategyIntent)
            .filter_by(
                user_id=self.user_id, approval_status="PENDING", status="PREVIEWED"
            )
            .order_by(StrategyIntent.created_at.desc())
            .all()
        )
        intent = next(
            (
                row
                for row in pending
                if secrets.compare_digest(
                    row.confirmation_token_hash or "", confirmation_hash(confirmation)
                )
            ),
            None,
        )
        if not intent:
            raise ValueError(
                "No pending activation preview matches this exact confirmation"
            )
        activation, run = activate_strategy(
            self.db, self.user_id, intent.strategy_id, intent.id, confirmation
        )
        return ToolResult(
            "activate_strategy",
            {"activation": serialize_activation(activation), "run": serialize_run(run)},
            f"Runtime acknowledged {run.execution_mode} strategy run {run.runtime_run_id}",
        )

    def _transition_strategy(self, action: str) -> ToolResult:
        from apps.api.services.strategy_control_service import (
            serialize_run,
            transition_strategy,
        )

        strategy = self._latest_strategy()
        run = transition_strategy(self.db, self.user_id, strategy.id, action)
        return ToolResult(
            f"{action}_strategy",
            serialize_run(run),
            f"Strategy runtime is {run.status}",
        )

    def pause_strategy(self) -> ToolResult:
        return self._transition_strategy("pause")

    def resume_strategy(self) -> ToolResult:
        return self._transition_strategy("resume")

    def stop_strategy(self) -> ToolResult:
        return self._transition_strategy("stop")

    def reconcile_account_tool(self) -> ToolResult:
        from apps.api.services.trading_service import reconcile_account

        account = (
            self.db.query(TradingAccount)
            .filter_by(user_id=self.user_id, venue="MOCK")
            .first()
        )
        if not account:
            raise ValueError("No paper account is available")
        row = reconcile_account(self.db, self.user_id, account.id)
        return ToolResult(
            "reconcile_account",
            {
                "id": row.id,
                "status": row.status,
                "differences": row.differences_json,
                "actions": row.actions_json,
            },
            f"Account reconciliation is {row.status}",
        )

    def generate_order_preview(self, request: str, symbols: list[str]) -> ToolResult:
        return ToolResult(
            "generate_order_preview",
            {
                "request": request,
                "symbols": symbols,
                "status": "MISSING_STRUCTURED_PARAMETERS",
                "confirmationRequired": True,
            },
            "Manual order was not submitted. Use the order preview form with account, quantity, notional, leverage, and mode; a second explicit confirmation is always required",
        )

    def get_market_quote(self, symbols: list[str]) -> ToolResult:
        rows = []
        sources = []
        for symbol in symbols[:12]:
            row = (
                self.db.query(MarketQuoteRecord)
                .filter(MarketQuoteRecord.base_asset == symbol.upper())
                .order_by(MarketQuoteRecord.fetched_at.desc())
                .first()
            )
            if not row:
                continue
            age = (datetime.now(timezone.utc) - _aware(row.fetched_at)).total_seconds()
            rows.append(
                {
                    "symbol": row.base_asset,
                    "pair": row.symbol,
                    "price": _string(row.price),
                    "change24hPct": _string(row.change_24h_pct),
                    "volume24hBase": _string(row.volume_24h_base),
                    "volume24hQuote": _string(row.volume_24h_quote),
                    "provider": row.provider,
                    "sourceTimestamp": _iso(row.source_timestamp),
                    "fetchedAt": _iso(row.fetched_at),
                    "fresh": age <= 300,
                }
            )
            sources.append(
                ToolSource(
                    row.provider,
                    f"{row.symbol} 24h ticker",
                    _provenance_url(row),
                    None,
                    row.source_timestamp,
                    row.fetched_at,
                )
            )
        summary = (
            f"Retrieved {len(rows)} persisted market quotes"
            if rows
            else "No synchronized market quote is available"
        )
        return ToolResult("get_market_quote", rows, summary, sources)

    def get_market_history(self, symbol: str, limit: int = 50) -> ToolResult:
        rows = (
            self.db.query(MarketQuoteRecord)
            .filter(MarketQuoteRecord.base_asset == symbol.upper())
            .order_by(MarketQuoteRecord.fetched_at.desc())
            .limit(min(limit, 100))
            .all()
        )
        data = [
            {
                "price": _string(row.price),
                "sourceTimestamp": _iso(row.source_timestamp),
                "fetchedAt": _iso(row.fetched_at),
                "provider": row.provider,
            }
            for row in rows
        ]
        sources = [
            ToolSource(
                row.provider,
                f"{row.symbol} quote history",
                _provenance_url(row),
                None,
                row.source_timestamp,
                row.fetched_at,
            )
            for row in rows[:5]
        ]
        return ToolResult(
            "get_market_history",
            data,
            f"Retrieved {len(data)} quote observations",
            sources,
        )

    def get_recent_news(
        self, hours: int = 48, symbols: list[str] | None = None
    ) -> ToolResult:
        return self.search_news(query="", symbols=symbols or [], hours=hours)

    def search_news(
        self, query: str, symbols: list[str] | None = None, hours: int = 72
    ) -> ToolResult:
        unified = self.search_source_documents(
            query=query, symbols=symbols, providers=["rss", "bloomberg"], hours=hours
        )
        if unified.data:
            return ToolResult(
                "search_news", unified.data, unified.summary, unified.sources
            )
        cutoff = datetime.now(timezone.utc) - timedelta(hours=min(max(hours, 1), 720))
        q = self.db.query(NewsItem).filter(NewsItem.fetched_at >= cutoff)
        words = [
            word.lower()
            for word in re.findall(r"[A-Za-z]{4,}", query)
            if word.lower() not in {"what", "with", "from", "market", "about"}
        ][:5]
        rows = (
            q.order_by(NewsItem.published_at.desc(), NewsItem.fetched_at.desc())
            .limit(100)
            .all()
        )
        filtered = []
        for row in rows:
            haystack = f"{row.title} {row.summary or ''}".lower()
            symbol_match = not symbols or any(
                symbol.upper() in (row.related_symbols or []) for symbol in symbols
            )
            word_match = not words or any(word in haystack for word in words)
            if symbol_match and word_match:
                filtered.append(row)
            if len(filtered) >= 12:
                break
        data = [
            {
                "source": row.source,
                "title": row.title,
                "summary": row.summary,
                "url": row.url,
                "publishedAt": _iso(row.published_at),
                "fetchedAt": _iso(row.fetched_at),
                "sentiment": row.sentiment_label,
                "symbols": row.related_symbols,
            }
            for row in filtered
        ]
        sources = [
            ToolSource(
                "rss",
                row.title,
                row.url,
                row.published_at,
                row.published_at,
                row.fetched_at,
            )
            for row in filtered
        ]
        return ToolResult(
            "search_news",
            data,
            f"Retrieved {len(data)} synchronized RSS items"
            if data
            else "No matching synchronized RSS news is available",
            sources,
        )

    def search_source_documents(
        self,
        query: str = "",
        symbols: list[str] | None = None,
        providers: list[str] | None = None,
        topics: list[str] | None = None,
        authors: list[str] | None = None,
        hours: int = 72,
    ) -> ToolResult:
        allowed_providers = [provider for provider in ("rss", "fintwit", "x-twitter", "bloomberg") if self._provider_allowed(provider)]
        requested_providers = [provider for provider in (providers or allowed_providers) if provider in allowed_providers]
        cutoff = datetime.now(timezone.utc) - timedelta(hours=min(max(hours, 1), 720))
        q = self.db.query(NormalizedDocument).filter(
            NormalizedDocument.created_at >= cutoff,
            NormalizedDocument.provider.in_(requested_providers),
        )
        if not get_settings().allow_nonredistributable_llm_input:
            q = q.filter(NormalizedDocument.redistribution_allowed.is_(True))
        rows = (
            q.order_by(
                NormalizedDocument.published_at.desc(),
                NormalizedDocument.created_at.desc(),
            )
            .limit(300)
            .all()
        )
        words = [
            word.lower()
            for word in re.findall(r"[A-Za-z]{4,}", query)
            if word.lower()
            not in {"what", "with", "from", "market", "about", "which", "recent"}
        ][:8]
        selected = []
        for row in rows:
            haystack = f"{row.title} {row.summary} {row.content}".lower()
            if symbols and not any(
                symbol.upper() in (row.symbols or []) for symbol in symbols
            ):
                continue
            if topics and not any(
                topic.lower() in {item.lower() for item in (row.topics or [])}
                for topic in topics
            ):
                continue
            if authors and (row.author or "").lower() not in {
                item.lower().lstrip("@") for item in authors
            }:
                continue
            if words and not any(word in haystack for word in words):
                continue
            selected.append(row)
            if len(selected) >= 20:
                break
        data = [
            {
                "provider": row.provider,
                "sourceType": row.source_type,
                "evidenceType": "source_opinion"
                if "opinion" in row.source_type
                else "reported_fact",
                "source": row.source_name,
                "author": row.author,
                "title": row.title,
                "summary": row.summary,
                "url": row.url,
                "publishedAt": _iso(row.published_at),
                "fetchedAt": _iso(row.created_at),
                "symbols": row.symbols,
                "topics": row.topics,
                "sentiment": row.sentiment,
                "credibilityScore": row.credibility_score,
                "weightedScore": row.final_score,
                "eventFingerprint": row.event_fingerprint,
                "licenseStatus": row.license_status,
            }
            for row in selected
        ]
        sources = [
            ToolSource(
                row.provider,
                row.title,
                row.url,
                row.published_at,
                row.published_at,
                row.created_at,
            )
            for row in selected
        ]
        summary = (
            f"Retrieved {len(selected)} traceable documents from {len({row.provider for row in selected})} providers"
            if selected
            else "Connected sources do not contain enough matching evidence"
        )
        return ToolResult("search_source_documents", data, summary, sources)

    def _provider_allowed(self, provider: str) -> bool:
        return provider in self.allowed_data_sources or (provider == "x-twitter" and "x" in self.allowed_data_sources)

    def get_defi_protocol_metrics(self, query: str = "") -> ToolResult:
        rows = (
            self.db.query(DefiMetric)
            .order_by(DefiMetric.fetched_at.desc())
            .limit(200)
            .all()
        )
        words = [word.lower() for word in re.findall(r"[A-Za-z0-9-]{3,}", query)][:10]
        selected = [
            row
            for row in rows
            if not words
            or any(
                word in f"{row.entity_name} {row.chain or ''} {row.metric_type}".lower()
                for word in words
            )
        ][:20]
        if not selected:
            selected = rows[:12]
        data = [
            {
                "entity": row.entity_name,
                "entityType": row.entity_type,
                "chain": row.chain,
                "metric": row.metric_type,
                "value": _string(row.value),
                "currency": row.currency,
                "fetchedAt": _iso(row.fetched_at),
            }
            for row in selected
        ]
        sources = [
            ToolSource(
                "defillama",
                f"{row.entity_name} {row.metric_type}",
                _provenance_url(row),
                None,
                row.source_timestamp,
                row.fetched_at,
            )
            for row in selected[:10]
        ]
        return ToolResult(
            "get_defi_protocol_metrics",
            data,
            f"Retrieved {len(data)} DefiLlama metrics"
            if data
            else "No synchronized DefiLlama metrics are available",
            sources,
        )

    def get_chain_metrics(self) -> ToolResult:
        rows = (
            self.db.query(OnchainMetric)
            .order_by(OnchainMetric.fetched_at.desc())
            .limit(50)
            .all()
        )
        data = [
            {
                "provider": row.provider,
                "chain": row.chain,
                "entity": row.entity_id,
                "metric": row.metric_type,
                "value": row.value,
                "blockNumber": row.block_number,
                "sourceTimestamp": _iso(row.source_timestamp),
                "fetchedAt": _iso(row.fetched_at),
            }
            for row in rows
        ]
        sources = [
            ToolSource(
                row.provider,
                f"{row.chain} {row.metric_type}",
                _provenance_url(row),
                None,
                row.source_timestamp,
                row.fetched_at,
            )
            for row in rows[:10]
        ]
        return ToolResult(
            "get_chain_metrics",
            data,
            f"Retrieved {len(data)} on-chain metrics"
            if data
            else "No synchronized on-chain metrics are available",
            sources,
        )

    def get_data_source_status(self) -> ToolResult:
        from apps.api.services.data_source_service import data_capability

        rows = self.db.query(DataSource).order_by(DataSource.name).all()
        data = [{"name": row.name, "items": row.item_count, **data_capability(self.db, row, self.user_id)} for row in rows]
        return ToolResult(
            "get_data_source_status",
            data,
            f"Retrieved status for {len(data)} data sources",
        )

    # ── NautilusTrader strategy research tools ──

    def run_nautilus_backtest(
        self, symbols: list[str], lookback_days: int = 90
    ) -> ToolResult:
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
            sources.append(
                ToolSource(
                    "nautilus_trader",
                    f"{symbol} backtest ({result.get('engine', 'unknown')})",
                    None,
                    None,
                    None,
                    datetime.now(timezone.utc),
                )
            )
        summary = (
            f"Ran NautilusTrader backtests for {len(results)} assets"
            if results
            else "No backtest results available"
        )
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
        sources = [
            ToolSource(
                result.get("engine", "nautilus_trader"),
                f"{strategy_name} on {asset}",
                None,
                None,
                None,
                datetime.now(timezone.utc),
            )
        ]
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
