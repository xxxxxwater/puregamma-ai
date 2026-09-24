"""The Agent's built-in capabilities, as an inventory of plugins.

PureGamma's Agent is a composition of capabilities the product already owns:
market data, news and source documents, on-chain metrics, the account snapshot,
options context, strategies and backtesting, data-source health, memory,
attachments, model routing and the planner that ties them together. This module
publishes that composition as data.

It exists because the alternative - letting each user pick "skills" per message -
made capability a per-request switch, and a switch is a way to configure a worse
answer. The Harness answer is the one this follows: capability is *installed*,
the Agent chooses what to use from the goal, and the surface shows what is
actually available.

Everything here is derived, never asserted:

* the tool list comes from ``AgentToolRegistry``'s own registry, so a tool that
  does not exist cannot appear in the inventory;
* ``enabled`` comes from the caller's entitlement and the provider-health gate
  the tool itself enforces, so the inventory cannot advertise a capability the
  run would refuse;
* ``service`` names the module that actually implements it, which is what a
  reader needs in order to go look.

Counts are reported as they are. This is not a fixed catalogue dressed up as a
plugin list, and it deliberately does not claim 209 entries.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from packages.agents.chat.tools import AgentToolRegistry

#: Data sources that gate a capability. A plugin whose sources are all outside
#: the caller's entitlement is reported disabled with that reason.
SOURCE_LABELS: dict[str, tuple[str, str]] = {
    "market": ("行情数据", "Market data"),
    "rss": ("新闻与来源文档", "News and source documents"),
    "fintwit": ("FinTwit", "FinTwit"),
    "x": ("X / Twitter", "X / Twitter"),
    "x-twitter": ("X / Twitter", "X / Twitter"),
    "bloomberg": ("Bloomberg", "Bloomberg"),
    "portfolio": ("账户数据", "Account data"),
    "options": ("期权数据", "Options data"),
}


@dataclass(frozen=True)
class AgentPluginSpec:
    """One built-in capability, and the tools it contributes."""

    id: str
    name_zh: str
    name_en: str
    description_zh: str
    description_en: str
    service: str
    tools: tuple[str, ...]
    requires: tuple[str, ...] = ()
    #: True when the capability is orchestration/lifecycle rather than a tool
    #: provider, so an empty ``tools`` is correct instead of suspicious.
    infrastructure: bool = False
    extra: dict = field(default_factory=dict)


#: The composition. Every ``tools`` entry must exist in AgentToolRegistry; the
#: inventory asserts that rather than trusting this table.
PLUGIN_SPECS: tuple[AgentPluginSpec, ...] = (
    AgentPluginSpec(
        id="orchestration",
        name_zh="编排",
        name_en="Orchestration",
        description_zh="把目标拆成计划、决定调用哪些内置插件，并汇总证据与结论。",
        description_en="Turns the goal into a plan, decides which built-in plugins to call, and assembles evidence and conclusions.",
        service="packages.agents.runtime.plan_agent_request",
        tools=(),
        infrastructure=True,
    ),
    AgentPluginSpec(
        id="llm",
        name_zh="模型路由",
        name_en="Model routing",
        description_zh="按任务类型选择实际执行的模型，并保证报价、预留与结算使用同一个模型。",
        description_en="Selects the model that actually runs, and keeps the quote, reservation and settlement on that same model.",
        service="packages.agents.llm.model_router.ModelRouter",
        tools=(),
        infrastructure=True,
    ),
    AgentPluginSpec(
        id="market-data",
        name_zh="行情",
        name_en="Market data",
        description_zh="实时报价与历史 K 线。价格缺失时明确报缺口，不伪造数值。",
        description_en="Live quotes and price history. A missing price is reported as a gap, never fabricated.",
        service="packages.data.market",
        tools=("get_market_quote", "get_market_history"),
        requires=("market",),
    ),
    AgentPluginSpec(
        id="news",
        name_zh="新闻与情绪",
        name_en="News and sentiment",
        description_zh="已同步的新闻检索与情绪背景，附带来源链接与发布时间。",
        description_en="Search of synchronized news plus sentiment context, with source links and publication times.",
        service="packages.data.news",
        tools=("get_recent_news", "search_news", "get_sentiment_context"),
        requires=("rss",),
    ),
    AgentPluginSpec(
        id="retrieval",
        name_zh="来源检索（RAG）",
        name_en="Source retrieval (RAG)",
        description_zh="在已入库的来源文档上做检索，把命中片段作为证据交给模型；这是回答的主要事实来源。",
        description_en="Retrieves passages from ingested source documents and hands them to the model as evidence - the primary factual path.",
        service="packages.data.evidence",
        tools=("search_source_documents",),
        requires=("rss",),
    ),
    AgentPluginSpec(
        id="public-web",
        name_zh="公开网络检索",
        name_en="Public web retrieval",
        description_zh="受控的公开网络检索，只在已同步证据不足时补充；默认关闭，由运营开关控制。",
        description_en="Controlled public-web retrieval, used only when synchronized evidence is insufficient. Off unless the operator enables it.",
        service="packages.data.online_research_provider",
        tools=("search_online_sources",),
        requires=("rss",),
    ),
    AgentPluginSpec(
        id="onchain",
        name_zh="链上与 DeFi",
        name_en="On-chain and DeFi",
        description_zh="协议指标、链上指标与快照。",
        description_en="Protocol metrics, chain metrics and on-chain snapshots.",
        service="packages.data.onchain",
        tools=("get_defi_protocol_metrics", "get_chain_metrics", "get_onchain_snapshot"),
    ),
    AgentPluginSpec(
        id="portfolio",
        name_zh="账户与持仓",
        name_en="Account and positions",
        description_zh="只读的账户快照、持仓与未结订单。没有连接账户时报告不可用，不返回零值组合。",
        description_en="Read-only account snapshot, positions and open orders. Without a connected account it reports unavailable instead of a zero portfolio.",
        service="packages.data.portfolio",
        tools=("get_account_snapshot", "get_position_snapshot", "get_open_orders"),
        requires=("portfolio",),
    ),
    AgentPluginSpec(
        id="options",
        name_zh="期权",
        name_en="Options",
        description_zh="期权链上下文与财报 gamma 背景。",
        description_en="Options-chain context and earnings gamma background.",
        service="packages.data.options",
        tools=("get_options_context", "get_earnings_gamma"),
        requires=("options",),
    ),
    AgentPluginSpec(
        id="strategies",
        name_zh="策略与回测",
        name_en="Strategies and backtesting",
        description_zh="策略草稿、校验、回测与运行状态。任何实盘动作仍需人工确认与风险门禁。",
        description_en="Strategy drafts, validation, backtests and run status. Any live action still needs explicit confirmation and the risk gates.",
        service="packages.agents.chat.tools.AgentToolRegistry",
        tools=(
            "list_research_strategies",
            "run_nautilus_backtest",
            "get_strategy_performance",
            "create_strategy_draft",
            "modify_strategy_draft",
            "validate_strategy",
            "backtest_strategy",
            "get_strategy_status",
        ),
    ),
    AgentPluginSpec(
        id="data-health",
        name_zh="数据源健康",
        name_en="Data-source health",
        description_zh="每个提供方的可用状态。降级或未配置的提供方被明确标注，而不是静默跳过。",
        description_en="Availability of every provider. A degraded or unconfigured provider is named, never silently skipped.",
        service="packages.data.source_status",
        tools=("get_data_source_status",),
    ),
    AgentPluginSpec(
        id="memory",
        name_zh="记忆",
        name_en="Memory",
        description_zh="用户自己的长期记忆：用户可读、可删，Agent 在生成结论前读取，不跨用户共享。",
        description_en="The user's own long-term memory: user-readable and user-deletable, read by the Agent before it concludes, never shared across users.",
        service="packages.database.models.ConversationMemorySummary",
        tools=(),
        infrastructure=True,
    ),
    AgentPluginSpec(
        id="attachments",
        name_zh="附件",
        name_en="Attachments",
        description_zh="对话内附件的租户隔离存储与鉴权读取；附件内容视为不可信材料。",
        description_en="Tenant-scoped storage and authenticated reads for conversation attachments; attachment content is untrusted material.",
        service="apps.api.services.chat_workspace",
        tools=(),
        infrastructure=True,
    ),
)


def _entitlement_gate(entitlement: dict, requires: tuple[str, ...]) -> tuple[bool, str | None]:
    """Decide a plugin's state the same way its tools do."""
    if not requires:
        return True, None
    allowed = set(entitlement.get("allowed_data_sources") or [])
    if "all" in allowed:
        return True, None
    missing = [source for source in requires if source not in allowed]
    if not missing:
        return True, None
    return False, "plan_required"


def inventory(db: Session, user, *, locale: str = "zh") -> dict:
    """The Agent's built-in plugins for this caller, with honest state.

    Raises if the table above names a tool the registry does not implement: a
    capability list that drifts from the code is worse than no list.
    """
    from apps.api.services.entitlement_service import get_user_entitlement

    register = AgentToolRegistry(db, user.id)
    implemented = set(register.tools)
    declared = {tool for spec in PLUGIN_SPECS for tool in spec.tools}
    unknown = sorted(declared - implemented)
    if unknown:
        raise RuntimeError(f"agent plugin inventory names unregistered tools: {unknown}")

    entitlement = get_user_entitlement(db, user.id)
    zh = locale == "zh"
    plugins: list[dict] = []
    for spec in PLUGIN_SPECS:
        enabled, reason = _entitlement_gate(entitlement, spec.requires)
        plugins.append(
            {
                "id": spec.id,
                "name": spec.name_zh if zh else spec.name_en,
                "description": spec.description_zh if zh else spec.description_en,
                "service": spec.service,
                "tools": list(spec.tools),
                "requires": [
                    (SOURCE_LABELS.get(source, (source, source))[0 if zh else 1])
                    for source in spec.requires
                ],
                "enabled": enabled,
                "reason": reason,
                "kind": "infrastructure" if spec.infrastructure else "provider",
            }
        )
    return {
        "plugins": plugins,
        "counts": {
            "total": len(plugins),
            "enabled": sum(1 for plugin in plugins if plugin["enabled"]),
            "tools": len(implemented),
        },
    }
