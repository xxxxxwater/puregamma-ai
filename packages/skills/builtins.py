from __future__ import annotations

import hashlib
import json
import uuid

from packages.skills.manifest import SkillManifest


NAMESPACE = uuid.UUID("36bc22a6-5ae8-4a7d-9f6c-7fb332b30f57")


def _id(slug: str) -> str:
    return str(uuid.uuid5(NAMESPACE, slug))


def _manifest(
    slug: str,
    name: str,
    description: str,
    *,
    assets: list[str],
    sources: list[str],
    tools: list[str],
    prompt: str,
    risk: str = "low",
    max_credits: int = 30,
    version: str = "1.0.0",
    changelog: str = "Migrated from the original Agent Chat capability selector.",
) -> tuple[SkillManifest, dict[str, str]]:
    files = {
        ".puregamma-skill.yaml": "generated from the signed PureGamma built-in catalog",
        f"prompts/{slug}.md": prompt,
    }
    return (
        SkillManifest(
            skill_id=_id(slug),
            slug=slug,
            name=name,
            description=description,
            publisher="PureGamma AI",
            asset_classes=assets,
            data_sources=sources,
            tool_allowlist=tools,
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            output_schema={"type": "object", "properties": {"answer": {"type": "string"}, "citations": {"type": "array", "items": {"type": "object"}}}},
            prompt_template_ref=f"prompts/{slug}.md",
            risk_level=risk,
            allow_autopilot=slug in {"market_research", "news_research", "portfolio_review", "source_check"},
            allow_order_intent=False,
            billing_type="included",
            version=version,
            release_status="published",
            scope="official",
            runtime={"max_calls_per_hour": 120, "max_credits_per_run": max_credits, "timeout_seconds": 90, "human_confirmation_required": False},
            tags=[slug, "official", "evidence-first"],
            changelog=changelog,
        ),
        files,
    )


BUILTIN_SKILLS = [
    _manifest(
        "market_research", "Market Research", "Evidence-based market structure, price, and trend research.",
        assets=["crypto", "equities", "multi_asset"], sources=["market", "rss", "fintwit", "x", "x-twitter", "bloomberg"],
        tools=["get_market_quote", "get_market_history", "search_source_documents", "search_online_sources", "get_data_source_status"],
        prompt="Build the current-market evidence pack before synthesis. First call get_data_source_status and treat DEGRADED, ERROR, NEED_KEY, or NOT_CONNECTED providers as unavailable: state their unavailability once, then continue with the remaining healthy providers instead of stopping. Pair a fresh timestamped quote with traceable source documents. Search the controlled public web only when synchronized documents are insufficient. Separate observations, reported facts, source opinion, calculations, and inference. Always deliver the best partial answer from available evidence and end with a short 'evidence gaps' list; never fill gaps from model memory.",
        version="1.3.0",
        changelog="Add data-health self-check with graceful degradation and explicit evidence-gap reporting.",
    ),
    _manifest(
        "news_research", "News Research", "Fresh, source-attributed news and market narrative research.",
        assets=["crypto", "equities", "multi_asset"], sources=["rss", "fintwit", "x", "x-twitter", "bloomberg"],
        tools=["get_recent_news", "search_news", "search_source_documents", "search_online_sources", "get_sentiment_context"],
        prompt="Cluster repeated reports, distinguish reporting from opinion, and attach URLs and publication timestamps. When a news provider is unavailable (missing key, license, or sync error), say so once and continue with the remaining providers; never present a partial feed as the complete picture.",
        version="1.2.0",
        changelog="Require explicit provider-availability disclosure when parts of the news pipeline are down.",
    ),
    _manifest(
        "portfolio_review", "Portfolio Review", "Personal portfolio exposure, position, and risk-context review.",
        assets=["portfolio", "multi_asset"], sources=["portfolio", "market"],
        tools=["get_account_snapshot", "get_position_snapshot", "get_open_orders", "get_market_quote"],
        prompt="Use only the authenticated user's portfolio facts. Lead with the NAV summary: total NAV, 24h change in USD and percent, available cash, and per-account breakdown. Then discuss the largest holdings with their chain, oracle price, weight, and 24h change, and call out concentration, stablecoin share, and notable movers. Mark missing prices, stale snapshots, unverified contracts, fallback-priced native assets, and partial data. When no portfolio account is connected, say so plainly, explain what the review would cover once connected, and point to the Integrations page instead of returning a generic empty answer.",
        version="1.2.0",
        changelog="Require NAV-first summary with 24h asset changes, chain breakdown, and oracle-price holdings discussion.",
    ),
    _manifest(
        "options_analysis", "Options Analysis", "Options surface, Greeks, and long-gamma research.",
        assets=["options", "crypto", "equities"], sources=["options", "market"],
        tools=["get_options_context", "get_earnings_gamma", "get_market_quote"],
        prompt="State expiry, strike, timestamp, liquidity limitations, and assumptions for every options conclusion. When the options data feed is unavailable or stale, mark the affected instruments and limit conclusions to what fresh data supports.",
        risk="medium",
        version="1.1.0",
        changelog="Add stale-feed marking and per-instrument availability scoping.",
    ),
    _manifest(
        "source_check", "Source Verification", "Provenance, freshness, licensing, and cross-source verification.",
        assets=["multi_asset"], sources=["rss", "fintwit", "x", "x-twitter", "bloomberg", "market"],
        tools=["get_data_source_status", "search_source_documents", "search_online_sources"],
        prompt="Do not infer truth from repetition. Report provenance, freshness, corroboration, and unresolved conflicts. Begin with get_data_source_status so the verification report can separate 'no corroboration found' from 'corroboration channel unavailable', and list unavailable channels explicitly.",
        version="1.2.0",
        changelog="Distinguish missing corroboration from unavailable corroboration channels.",
    ),
    _manifest(
        "deep_research", "Deep Research", "Broader multi-source research with a higher evidence and cost budget.",
        assets=["crypto", "options", "equities", "portfolio", "defi", "macro", "multi_asset"],
        sources=["market", "rss", "fintwit", "x", "x-twitter", "bloomberg", "portfolio", "options", "onchain", "defillama"],
        tools=["get_market_quote", "get_market_history", "search_source_documents", "search_online_sources", "get_defi_protocol_metrics", "get_chain_metrics", "get_data_source_status", "get_account_snapshot", "get_position_snapshot", "get_options_context", "list_research_strategies", "run_nautilus_backtest", "get_strategy_performance"],
        prompt="Build an evidence pack before synthesis. Present competing hypotheses, missing evidence, timestamps, and citations. When the user asks about strategy quality or a trading idea, prefer validating it with run_nautilus_backtest and get_strategy_performance over narrative-only reasoning, and report the backtest window, assumptions, and key performance metrics alongside the thesis. Skip unavailable providers with a one-line disclosure instead of aborting the research.",
        risk="medium", max_credits=150, version="1.2.0",
        changelog="Route strategy-quality questions through backtest validation and add graceful provider degradation.",
    ),
]


# Keep previously published manifests available for pinned installations and
# replayable SkillRun audits. The latest manifest for each slug remains in
# BUILTIN_SKILLS and is applied last by seed_official_skills.
LEGACY_BUILTIN_SKILLS = [
    _manifest(
        "market_research", "Market Research", "Evidence-based market structure, price, and trend research.",
        assets=["crypto", "equities", "multi_asset"], sources=["market", "rss", "fintwit", "x", "x-twitter", "bloomberg"],
        tools=["get_market_quote", "get_market_history", "search_source_documents", "search_online_sources", "get_data_source_status"],
        prompt="Build the current-market evidence pack before synthesis. Pair a fresh timestamped quote with traceable source documents. Search the controlled public web only when synchronized documents are insufficient. Separate observations, reported facts, source opinion, calculations, and inference. If either live price evidence or current source evidence remains missing, state that evidence is insufficient instead of filling the gap from model memory.",
        version="1.2.0",
        changelog="Add controlled online source discovery after synchronized pipeline evidence is insufficient.",
    ),
    _manifest(
        "news_research", "News Research", "Fresh, source-attributed news and market narrative research.",
        assets=["crypto", "equities", "multi_asset"], sources=["rss", "fintwit", "x", "x-twitter", "bloomberg"],
        tools=["get_recent_news", "search_news", "search_source_documents", "search_online_sources", "get_sentiment_context"],
        prompt="Cluster repeated reports, distinguish reporting from opinion, and attach URLs and publication timestamps.",
        version="1.1.0",
        changelog="Add controlled online source discovery after synchronized news evidence is insufficient.",
    ),
    _manifest(
        "portfolio_review", "Portfolio Review", "Personal portfolio exposure, position, and risk-context review.",
        assets=["portfolio", "multi_asset"], sources=["portfolio", "market"],
        tools=["get_account_snapshot", "get_position_snapshot", "get_open_orders", "get_market_quote"],
        prompt="Use only the authenticated user's portfolio facts. Mark missing prices, stale snapshots, and partial data. When no portfolio account is connected, say so plainly, explain what the review would cover once connected, and point to the Integrations page instead of returning a generic empty answer.",
        version="1.1.0",
        changelog="Add unconnected-portfolio guidance instead of empty responses.",
    ),
    _manifest(
        "portfolio_review", "Portfolio Review", "Personal portfolio exposure, position, and risk-context review.",
        assets=["portfolio", "multi_asset"], sources=["portfolio", "market"],
        tools=["get_account_snapshot", "get_position_snapshot", "get_open_orders", "get_market_quote"],
        prompt="Use only the authenticated user's portfolio facts. Mark missing prices, stale snapshots, and partial data.",
    ),
    _manifest(
        "options_analysis", "Options Analysis", "Options surface, Greeks, and long-gamma research.",
        assets=["options", "crypto", "equities"], sources=["options", "market"],
        tools=["get_options_context", "get_earnings_gamma", "get_market_quote"],
        prompt="State expiry, strike, timestamp, liquidity limitations, and assumptions for every options conclusion.",
        risk="medium",
    ),
    _manifest(
        "source_check", "Source Verification", "Provenance, freshness, licensing, and cross-source verification.",
        assets=["multi_asset"], sources=["rss", "fintwit", "x", "x-twitter", "bloomberg", "market"],
        tools=["get_data_source_status", "search_source_documents", "search_online_sources"],
        prompt="Do not infer truth from repetition. Report provenance, freshness, corroboration, and unresolved conflicts.",
        version="1.1.0",
        changelog="Add controlled public-web metadata for source verification gaps.",
    ),
    _manifest(
        "deep_research", "Deep Research", "Broader multi-source research with a higher evidence and cost budget.",
        assets=["crypto", "options", "equities", "portfolio", "defi", "macro", "multi_asset"],
        sources=["market", "rss", "fintwit", "x", "x-twitter", "bloomberg", "portfolio", "options", "onchain", "defillama"],
        tools=["get_market_quote", "get_market_history", "search_source_documents", "search_online_sources", "get_defi_protocol_metrics", "get_chain_metrics", "get_data_source_status", "get_account_snapshot", "get_position_snapshot", "get_options_context", "list_research_strategies", "run_nautilus_backtest", "get_strategy_performance"],
        prompt="Build an evidence pack before synthesis. Present competing hypotheses, missing evidence, timestamps, and citations.",
        risk="medium", max_credits=150, version="1.1.0",
        changelog="Add controlled online source discovery for missing deep-research evidence.",
    ),
    _manifest(
        "market_research", "Market Research", "Evidence-based market structure, price, and trend research.",
        assets=["crypto", "equities", "multi_asset"], sources=["market", "rss", "fintwit", "x", "x-twitter", "bloomberg"],
        tools=["get_market_quote", "get_market_history", "search_source_documents", "get_data_source_status"],
        prompt="Build the current-market evidence pack before synthesis. Pair a fresh timestamped quote with traceable source documents. Separate observations, reported facts, source opinion, calculations, and inference. If either live price evidence or current source evidence is missing, state that evidence is insufficient instead of filling the gap from model memory.",
        version="1.1.0",
        changelog="Pair current market quotes with traceable document evidence and fail closed when either evidence class is unavailable.",
    ),
    # The original 1.0.0 release (restored): pinned installations and historical
    # SkillRun audits referencing market_research@1.0.0 must keep resolving.
    _manifest(
        "market_research", "Market Research", "Evidence-based market structure, price, and trend research.",
        assets=["crypto", "equities", "multi_asset"], sources=["market"],
        tools=["get_market_quote", "get_market_history", "get_data_source_status"],
        prompt="Separate current observations, calculations, and inference. Cite market timestamps and providers.",
    ),
    _manifest(
        "news_research", "News Research", "Fresh, source-attributed news and market narrative research.",
        assets=["crypto", "equities", "multi_asset"], sources=["rss", "fintwit", "x", "x-twitter", "bloomberg"],
        tools=["get_recent_news", "search_news", "search_source_documents", "get_sentiment_context"],
        prompt="Cluster repeated reports, distinguish reporting from opinion, and attach URLs and publication timestamps.",
        version="1.0.0",
    ),
    _manifest(
        "source_check", "Source Verification", "Provenance, freshness, licensing, and cross-source verification.",
        assets=["multi_asset"], sources=["rss", "fintwit", "x", "x-twitter", "bloomberg", "market"],
        tools=["get_data_source_status", "search_source_documents"],
        prompt="Do not infer truth from repetition. Report provenance, freshness, corroboration, and unresolved conflicts.",
        version="1.0.0",
    ),
    _manifest(
        "deep_research", "Deep Research", "Broader multi-source research with a higher evidence and cost budget.",
        assets=["crypto", "options", "equities", "portfolio", "defi", "macro", "multi_asset"],
        sources=["market", "rss", "fintwit", "x", "x-twitter", "bloomberg", "portfolio", "options", "onchain", "defillama"],
        tools=["get_market_quote", "get_market_history", "search_source_documents", "get_defi_protocol_metrics", "get_chain_metrics", "get_data_source_status", "get_account_snapshot", "get_position_snapshot", "get_options_context", "list_research_strategies", "run_nautilus_backtest", "get_strategy_performance"],
        prompt="Build an evidence pack before synthesis. Present competing hypotheses, missing evidence, timestamps, and citations.",
        risk="medium", max_credits=150, version="1.0.0",
    ),
]


def _workflow_manifest(
    slug: str,
    name: str,
    description: str,
    *,
    assets: list[str],
    sources: list[str],
    tools: list[str],
    prompt: str,
    workflow: str,
    input_schema: dict,
    output_schema: dict,
    risk: str = "low",
    max_credits: int = 20,
    timeout_seconds: int = 60,
    max_calls_per_hour: int = 60,
    version: str = "1.0.0",
) -> tuple[SkillManifest, dict[str, str]]:
    """Official declarative workflow Skill: a versioned DAG executed by the
    single deterministic engine in packages.skills.workflows."""
    files = {
        ".puregamma-skill.yaml": "generated from the signed PureGamma built-in workflow catalog",
        f"prompts/{slug}.md": prompt,
        f"workflows/{slug}.yaml": workflow,
    }
    return (
        SkillManifest(
            skill_id=_id(slug),
            slug=slug,
            name=name,
            description=description,
            publisher="PureGamma AI",
            asset_classes=assets,
            data_sources=sources,
            tool_allowlist=tools,
            input_schema=input_schema,
            output_schema=output_schema,
            prompt_template_ref=f"prompts/{slug}.md",
            workflow_template_ref=f"workflows/{slug}.yaml",
            risk_level=risk,
            allow_autopilot=True,
            allow_order_intent=False,
            billing_type="included",
            version=version,
            release_status="published",
            scope="official",
            evidence={"required": True, "require_source_timestamp": True, "require_citation_links": True, "allow_insufficient_evidence_result": True},
            runtime={"max_calls_per_hour": max_calls_per_hour, "max_credits_per_run": max_credits, "timeout_seconds": timeout_seconds, "human_confirmation_required": False},
            tags=[slug, "official", "workflow", "evidence-first"],
            changelog="Initial declarative workflow release.",
        ),
        files,
    )


WORKFLOW_BUILTIN_SKILLS = [
    _workflow_manifest(
        "overnight_market_brief", "Overnight Market Brief", "Evidence-first overnight market brief composed from stored research events with citations.",
        assets=["crypto", "equities", "multi_asset"], sources=["market", "rss"],
        tools=["get_market_quote", "get_recent_news", "get_data_source_status"],
        prompt="Answer only from stored research events and market evidence. Cite source URLs and publication timestamps; list evidence gaps instead of filling them.",
        workflow="""version: 1
steps:
  - id: overnight
    tool: research_overnight
    inputs_from: []
    required_evidence: []
    on_failure: abort
  - id: compose
    tool: compose_markdown
    inputs_from: [overnight]
    required_evidence: [market, news]
    on_failure: abort
    args:
      style: brief
output:
  brief_markdown: {from: compose, path: markdown}
  events: {from: overnight, path: events}
  health: {from: overnight, path: health}
""",
        input_schema={"type": "object", "properties": {"locale": {"type": "string", "enum": ["en", "zh"]}, "since_hours": {"type": "integer"}}},
        output_schema={"type": "object", "properties": {"brief_markdown": {"type": "string"}, "events": {"type": "array"}, "health": {"type": "object"}}, "required": ["brief_markdown", "events", "health"]},
        max_credits=20,
    ),
    _workflow_manifest(
        "portfolio_impact_review", "Portfolio Impact Review", "NAV-first review mapping stored research impacts onto the user's real holdings.",
        assets=["portfolio", "multi_asset"], sources=["portfolio", "market"],
        tools=["get_account_snapshot", "get_position_snapshot", "get_market_quote"],
        prompt="Use only the authenticated user's portfolio facts and stored research impacts. Lead with NAV, mark missing or stale data, and never invent holdings.",
        workflow="""version: 1
steps:
  - id: portfolio
    tool: get_account_snapshot
    inputs_from: []
    required_evidence: []
    on_failure: abort
  - id: impacts
    tool: research_portfolio_impact
    inputs_from: [portfolio]
    required_evidence: []
    on_failure: degrade
  - id: compose
    tool: compose_markdown
    inputs_from: [portfolio, impacts]
    required_evidence: [portfolio]
    on_failure: abort
    args:
      style: review
output:
  nav: {from: portfolio, path: total_nav}
  impacts: {from: impacts, path: impacts, default: []}
  gaps: {from: compose, path: gaps, default: []}
  review_markdown: {from: compose, path: markdown}
""",
        input_schema={"type": "object", "properties": {"locale": {"type": "string", "enum": ["en", "zh"]}, "cadence": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"nav": {}, "impacts": {"type": "array"}, "gaps": {"type": "array"}, "review_markdown": {"type": "string"}}, "required": ["nav", "impacts", "gaps"]},
        max_credits=20,
    ),
    _workflow_manifest(
        "earnings_event_map", "Earnings Event Map", "Upcoming confirmed earnings mapped to the user's holdings and watchlist. Confirmed dates only — never estimates.",
        assets=["equities", "portfolio"], sources=["portfolio"],
        tools=["get_account_snapshot", "get_position_snapshot"],
        prompt="Only confirmed earnings from the research pipeline may be presented. Estimated cadence entries must never appear; say so when coverage is empty.",
        workflow="""version: 1
steps:
  - id: earnings
    tool: confirmed_earnings
    inputs_from: []
    required_evidence: []
    on_failure: abort
  - id: map
    tool: map_holdings
    inputs_from: [earnings]
    required_evidence: []
    on_failure: abort
output:
  events: {from: earnings, path: events}
  mapped_assets: {from: map, path: mapped_assets, default: []}
""",
        input_schema={"type": "object", "properties": {"days": {"type": "integer"}, "locale": {"type": "string", "enum": ["en", "zh"]}}},
        output_schema={"type": "object", "properties": {"events": {"type": "array"}, "mapped_assets": {"type": "array"}}, "required": ["events", "mapped_assets"]},
        max_credits=15,
    ),
    _workflow_manifest(
        "long_gamma_scan", "Long Gamma Scan", "Ranked Deribit long-gamma candidates with full provenance and liquidity context.",
        assets=["options", "crypto"], sources=["options", "market"],
        tools=["get_options_context", "get_market_quote"],
        prompt="State expiry, strike, gamma, theta, spread, open interest, timestamp, and source for every candidate. Mark degraded feeds; research only, execution disabled.",
        workflow="""version: 1
steps:
  - id: scan
    tool: get_options_context
    inputs_from: []
    required_evidence: []
    on_failure: abort
  - id: rank
    tool: rank_candidates
    inputs_from: [scan]
    required_evidence: [options]
    on_failure: abort
output:
  candidates: {from: rank, path: candidates}
  as_of: {from: scan, path: as_of}
""",
        input_schema={"type": "object", "properties": {"currencies": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer"}, "locale": {"type": "string", "enum": ["en", "zh"]}}},
        output_schema={"type": "object", "properties": {"candidates": {"type": "array"}, "as_of": {"type": "string"}}, "required": ["candidates", "as_of"]},
        risk="medium", max_credits=25,
    ),
    _workflow_manifest(
        "opportunity_scan", "Opportunity Scan", "Merged research opportunities: long gamma, confirmed earnings, price moves, and stored signals with provenance.",
        assets=["options", "crypto", "equities", "multi_asset"], sources=["options", "market", "rss"],
        tools=["get_options_context", "get_recent_news", "get_market_quote", "get_data_source_status"],
        prompt="Every opportunity carries provenance (source, url, as_of). Degraded sources are listed in sources with their status instead of being hidden.",
        workflow="""version: 1
steps:
  - id: opportunities
    tool: research_opportunities
    inputs_from: []
    required_evidence: []
    on_failure: degrade
  - id: gamma
    tool: get_options_context
    inputs_from: []
    required_evidence: []
    on_failure: degrade
  - id: signals
    tool: signal_scan
    inputs_from: []
    required_evidence: []
    on_failure: degrade
  - id: merge
    tool: merge_opportunities
    inputs_from: [opportunities, gamma, signals]
    required_evidence: []
    on_failure: abort
output:
  opportunities: {from: merge, path: opportunities}
  sources: {from: merge, path: sources}
""",
        input_schema={"type": "object", "properties": {"locale": {"type": "string", "enum": ["en", "zh"]}, "limit": {"type": "integer"}}},
        output_schema={"type": "object", "properties": {"opportunities": {"type": "array"}, "sources": {"type": "array"}}, "required": ["opportunities", "sources"]},
        max_credits=30, timeout_seconds=90,
    ),
    _workflow_manifest(
        "strategy_backtest", "Strategy Backtest", "Validate a declarative strategy spec, enqueue an async backtest, and poll its status once.",
        assets=["crypto", "multi_asset"], sources=["market"],
        tools=["run_nautilus_backtest", "get_strategy_performance"],
        prompt="Backtests are hypothetical research over stored market data. Report run_id, status, assumptions, and metrics when completed; mark the run degraded when the backtest service is unavailable.",
        workflow="""version: 1
steps:
  - id: validate
    tool: validate_backtest_spec
    inputs_from: []
    required_evidence: []
    on_failure: abort
  - id: kickoff
    tool: run_nautilus_backtest
    inputs_from: [validate]
    required_evidence: []
    on_failure: degrade
output:
  run_id: {from: kickoff, path: run_id, default: null}
  status: {from: kickoff, path: status, default: unavailable}
  metrics: {from: kickoff, path: metrics, default: null}
""",
        input_schema={"type": "object", "properties": {"spec": {"type": "object"}, "window_days": {"type": "integer"}, "locale": {"type": "string", "enum": ["en", "zh"]}}, "required": ["spec"]},
        output_schema={"type": "object", "properties": {"run_id": {}, "status": {"type": "string"}, "metrics": {}}, "required": ["run_id", "status", "metrics"]},
        risk="medium", max_credits=80, timeout_seconds=120, max_calls_per_hour=20,
    ),
    _workflow_manifest(
        "execution_monitor", "Execution Monitor", "Read-only runtime, open-order, and risk-state monitor that surfaces anomalies. Never imports or mutates anything.",
        assets=["multi_asset", "portfolio"], sources=["portfolio", "market"],
        tools=["get_strategy_status", "get_open_orders", "get_account_snapshot", "get_data_source_status"],
        prompt="Read-only monitoring: report stored runtime status, open order intents, and paused risk budgets as anomalies. Never activate, pause, resume, stop, or reconcile anything.",
        workflow="""version: 1
steps:
  - id: runtime
    tool: get_strategy_status
    inputs_from: []
    required_evidence: []
    on_failure: degrade
  - id: orders
    tool: get_open_orders
    inputs_from: []
    required_evidence: []
    on_failure: degrade
  - id: risk
    tool: risk_state
    inputs_from: []
    required_evidence: []
    on_failure: degrade
  - id: anomalies
    tool: detect_anomalies
    inputs_from: [runtime, orders, risk]
    required_evidence: []
    on_failure: abort
output:
  status: {from: anomalies, path: status, default: ok}
  findings: {from: anomalies, path: findings, default: []}
""",
        input_schema={"type": "object", "properties": {"locale": {"type": "string", "enum": ["en", "zh"]}}},
        output_schema={"type": "object", "properties": {"status": {"type": "string"}, "findings": {"type": "array"}}, "required": ["status", "findings"]},
        max_credits=15,
    ),
]


def seed_official_skills(db) -> None:
    """Idempotently publish the official Skills: the six legacy Chat
    capabilities (plus their pinned legacy versions) and the seven declarative
    workflow Skills."""
    from packages.database.models import Skill, SkillPermission, SkillSource, SkillVersion, utcnow

    for manifest, files in [*LEGACY_BUILTIN_SKILLS, *BUILTIN_SKILLS, *WORKFLOW_BUILTIN_SKILLS]:
        canonical = json.dumps(
            {"manifest": manifest.model_dump(mode="json"), "files": files},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = hashlib.sha256(canonical.encode()).hexdigest()
        skill = db.get(Skill, manifest.skill_id) or Skill(id=manifest.skill_id)
        skill.slug = manifest.slug
        skill.name = manifest.name
        skill.description = manifest.description
        skill.publisher_name = manifest.publisher
        skill.owner_user_id = None
        skill.workspace_id = None
        skill.scope = "official"
        skill.status = "published"
        skill.current_version = manifest.version
        skill.asset_classes_json = manifest.asset_classes
        skill.risk_level = manifest.risk_level
        skill.billing_type = manifest.billing_type
        skill.allow_autopilot = manifest.allow_autopilot
        skill.allow_order_intent = manifest.allow_order_intent
        db.add(skill)
        db.flush()
        version = db.query(SkillVersion).filter_by(skill_id=skill.id, version=manifest.version).one_or_none()
        if not version:
            version = SkillVersion(
                skill_id=skill.id,
                version=manifest.version,
                manifest_json=manifest.model_dump(mode="json"),
                content_bundle_json=files,
                content_hash=content_hash,
                release_status="published",
                changelog=manifest.changelog,
                validation_json={"valid": True, "declarative_only": True, "built_in": True},
                published_at=utcnow(),
            )
            db.add(version)
            db.flush()
        if not db.query(SkillSource).filter_by(skill_version_id=version.id).first():
            db.add(SkillSource(
                skill_id=skill.id,
                skill_version_id=version.id,
                source_type="official",
                trust_status="trusted",
                metadata_json={"built_in": True, "content_hash": content_hash},
            ))
        existing_permissions = {
            (row.permission_type, row.resource)
            for row in db.query(SkillPermission).filter_by(skill_version_id=version.id).all()
        }
        for permission_type, resources in (("data_source", manifest.data_sources), ("tool", manifest.tool_allowlist)):
            for resource in resources:
                if (permission_type, resource) not in existing_permissions:
                    db.add(SkillPermission(
                        skill_id=skill.id,
                        skill_version_id=version.id,
                        permission_type=permission_type,
                        resource=resource,
                        effect="allow",
                        constraints_json={},
                    ))
