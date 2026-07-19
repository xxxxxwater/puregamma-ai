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
]


# Keep previously published manifests available for pinned installations and
# replayable SkillRun audits. The latest manifest for each slug remains in
# BUILTIN_SKILLS and is applied last by seed_official_skills.
LEGACY_BUILTIN_SKILLS = [
    _manifest(
        "market_research", "Market Research", "Evidence-based market structure, price, and trend research.",
        assets=["crypto", "equities", "multi_asset"], sources=["market", "rss", "fintwit", "x", "x-twitter", "bloomberg"],
        tools=["get_market_quote", "get_market_history", "search_source_documents", "get_data_source_status"],
        prompt="Build the current-market evidence pack before synthesis. Pair a fresh timestamped quote with traceable source documents. Separate observations, reported facts, source opinion, calculations, and inference. If either live price evidence or current source evidence is missing, state that evidence is insufficient instead of filling the gap from model memory.",
        version="1.1.0",
        changelog="Pair current market quotes with traceable document evidence and fail closed when either evidence class is unavailable.",
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


def seed_official_skills(db) -> None:
    """Idempotently publish the six legacy Chat capabilities as official Skills."""
    from packages.database.models import Skill, SkillPermission, SkillSource, SkillVersion, utcnow

    for manifest, files in [*LEGACY_BUILTIN_SKILLS, *BUILTIN_SKILLS]:
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
