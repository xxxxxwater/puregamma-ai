"""Workflow Skill engine + official workflow catalog tests (vertical slice P0-6)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from apps.api.services import skill_workflow_service
from apps.api.services.skill_service import skill_registry
from apps.api.services.skill_workflow_service import invoke_workflow_skill
from packages.database.models import (
    AccountSnapshot,
    Alert,
    BacktestRun,
    MarketEvent,
    PortfolioAutopilotReview,
    PositionSnapshot,
    ResearchSnapshot,
    Signal,
    Skill,
    SkillPermission,
    SkillRun,
    SkillVersion,
    TradingAccount,
    UserPreference,
    utcnow,
)
from packages.skills import workflows
from packages.skills.builtins import WORKFLOW_BUILTIN_SKILLS, seed_official_skills
from packages.skills.manifest import SkillManifest, validate_json_instance
from packages.skills.workflows import (
    TOOL_REGISTRY,
    ToolUnavailableError,
    WorkflowError,
    load_workflow_definition,
    run_workflow,
)
from packages.workers import tasks

WORKFLOW_SLUGS = [manifest.slug for manifest, _ in WORKFLOW_BUILTIN_SKILLS]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine_manifest(**overrides) -> SkillManifest:
    base = dict(
        skill_id="engine-test-skill",
        slug="engine_test",
        name="Engine Test",
        description="Synthetic workflow for engine tests.",
        publisher="Test",
        asset_classes=["crypto"],
        data_sources=["market"],
        tool_allowlist=["get_market_quote"],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk_level="low",
        allow_autopilot=False,
        allow_order_intent=False,
        billing_type="included",
        version="1.0.0",
        release_status="published",
        scope="official",
        runtime={"max_calls_per_hour": 10, "max_credits_per_run": 30, "timeout_seconds": 5, "human_confirmation_required": False},
    )
    base.update(overrides)
    return SkillManifest(**base)


@pytest.fixture()
def register_tool(monkeypatch):
    def _register(name: str, fn):
        monkeypatch.setitem(TOOL_REGISTRY, name, fn)

    return _register


def _ok_tool(name: str, calls: list[str], *, kind: str = "market_quote"):
    def _tool(ctx, args, deps):
        calls.append(name)
        return {"output": {"name": name}, "evidence": [{"kind": kind, "ref": name, "url": None, "published_at": None, "source": "test"}]}

    return _tool


def _seed_healthy_snapshot(db) -> None:
    now = utcnow()
    db.add(
        ResearchSnapshot(
            kind="intraday",
            as_of=now,
            data_cutoff_at=now,
            window_start=now - timedelta(hours=24),
            window_end=now,
            status="completed",
            health_json={"price_move": {"status": "ok", "last_success_at": now.isoformat(), "items": 1}, "news": {"status": "ok", "last_success_at": now.isoformat(), "items": 1}},
            source_counts_json={"price_move": 1, "news": 1},
        )
    )
    db.commit()


def _seed_event(db, *, event_type: str, title: str, url: str, kind: str, days_ahead: float = 0.0, summary: str = "summary") -> MarketEvent:
    now = utcnow()
    published = now + timedelta(days=days_ahead)
    event = MarketEvent(
        event_type=event_type,
        title=title,
        summary=summary,
        source_provider="test_provider",
        source_url=url,
        source_published_at=published,
        collected_at=now,
        data_cutoff_at=now,
        fingerprint=hashlib.sha256(f"{event_type}|{title}|{url}|{days_ahead}".encode()).hexdigest(),
        assets=["BTC"],
        direction="up",
        time_horizon="intraday",
        confidence=0.9,
        evidence_json=[{"kind": kind, "ref": f"test:{title}", "url": url, "published_at": published.isoformat()}],
        evidence_gaps=[],
        status="active",
    )
    db.add(event)
    db.commit()
    return event


def _healthy_chain(currency: str) -> dict:
    expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    instruments = [
        {
            "instrument": f"{currency}-30D-70000-C",
            "underlying": currency,
            "option_type": "call",
            "strike": 70000.0,
            "expiry": expiry,
            "volume_24h": 120.0,
            "open_interest": 800.0,
            "spread_pct": 0.01,
            "mark_iv": 55.0,
            "greeks": {"gamma": 0.002, "theta": -40.0},
            "timestamp": "2026-07-25T00:00:00+00:00",
        },
        {
            "instrument": f"{currency}-30D-65000-P",
            "underlying": currency,
            "option_type": "put",
            "strike": 65000.0,
            "expiry": expiry,
            "volume_24h": 90.0,
            "open_interest": 400.0,
            "spread_pct": 0.02,
            "mark_iv": 58.0,
            "greeks": {"gamma": 0.0015, "theta": -35.0},
            "timestamp": "2026-07-25T00:00:00+00:00",
        },
    ]
    return {
        "provider": "deribit_public",
        "status": "HEALTHY",
        "currency": currency,
        "fetched_at": "2026-07-25T00:00:00+00:00",
        "instruments": instruments,
        "source_url": "https://deribit.test/chain",
        "live_trading": False,
    }


@pytest.fixture()
def mock_deribit(monkeypatch):
    monkeypatch.setattr("apps.api.services.options_service.get_option_chain", lambda currency, **kwargs: _healthy_chain(currency))


def _connect_portfolio(db, user) -> TradingAccount:
    account = TradingAccount(
        user_id=user.id,
        name="Test Hyperliquid",
        venue="HYPERLIQUID",
        account_type="READ_ONLY",
        base_currency="USD",
        status="ACTIVE",
        permissions_json={},
    )
    db.add(account)
    db.flush()
    snapshot = AccountSnapshot(
        user_id=user.id,
        account_id=account.id,
        balance=1000.0,
        equity=1000.0,
        available_margin=500.0,
        daily_pnl=10.0,
        stale=False,
        raw_event_reference={},
        captured_at=utcnow(),
    )
    db.add(snapshot)
    db.add(
        PositionSnapshot(
            user_id=user.id,
            account_id=account.id,
            instrument="BTC",
            quantity=0.1,
            side="long",
            average_price=60000.0,
            mark_price=62000.0,
            raw_event_reference={"value": 6200.0},
            captured_at=snapshot.captured_at,
        )
    )
    db.commit()
    return account


def _resolved(db, user, slug: str):
    return skill_registry(db, user).resolve_many([{"slug": slug}], enforce_rate_limit=False)[0]


def _workflow_output(run: SkillRun) -> dict:
    return (run.evidence_json or {}).get("workflow", {}).get("output") or {}


# ---------------------------------------------------------------------------
# DAG engine
# ---------------------------------------------------------------------------


def test_engine_executes_steps_in_dependency_order(db, normal_user, register_tool):
    calls: list[str] = []
    for name in ("fake_a", "fake_b", "fake_c"):
        register_tool(name, _ok_tool(name, calls))
    workflow_def = {
        "steps": [
            {"id": "c", "tool": "fake_c", "inputs_from": ["b"], "required_evidence": ["market"], "on_failure": "abort"},
            {"id": "a", "tool": "fake_a"},
            {"id": "b", "tool": "fake_b", "inputs_from": ["a"]},
        ],
        "output": {"last": {"from": "c", "path": "name"}},
    }
    result = run_workflow(db, user=normal_user, manifest=_engine_manifest(), workflow_def=workflow_def, inputs={})
    assert calls == ["fake_a", "fake_b", "fake_c"]
    assert result.status == "completed"
    assert [record["id"] for record in result.steps] == ["a", "b", "c"]
    assert result.output == {"last": "fake_c"}
    assert result.usage["credits_estimated"] == 30
    for record in result.steps:
        assert record["status"] == "ok"
        assert record["started_at"]
        assert record["latency_ms"] >= 0
        assert record["error"] is None
    assert result.evidence_refs[0]["kind"] == "market_quote"


def test_engine_degrade_continues_and_abort_halts(db, normal_user, register_tool):
    calls: list[str] = []
    register_tool("fake_ok", _ok_tool("fake_ok", calls))

    def _boom(ctx, args, deps):
        raise ToolUnavailableError("SOURCE_DOWN", "provider is down")

    register_tool("fake_boom", _boom)
    workflow_def = {
        "steps": [
            {"id": "a", "tool": "fake_ok"},
            {"id": "b", "tool": "fake_boom", "inputs_from": ["a"], "on_failure": "degrade"},
            {"id": "c", "tool": "fake_ok", "inputs_from": ["b"]},
        ]
    }
    result = run_workflow(db, user=normal_user, manifest=_engine_manifest(), workflow_def=workflow_def, inputs={})
    assert result.status == "degraded"
    assert result.degraded_steps == ["b"]
    statuses = {record["id"]: record["status"] for record in result.steps}
    assert statuses == {"a": "ok", "b": "degraded", "c": "ok"}
    assert next(record for record in result.steps if record["id"] == "b")["error"]["code"] == "SOURCE_DOWN"

    workflow_def["steps"][1]["on_failure"] = "abort"
    calls.clear()
    result = run_workflow(db, user=normal_user, manifest=_engine_manifest(), workflow_def=workflow_def, inputs={})
    assert result.status == "failed"
    assert result.error["code"] == "SOURCE_DOWN"
    statuses = {record["id"]: record["status"] for record in result.steps}
    assert statuses == {"a": "ok", "b": "failed", "c": "skipped"}


def test_engine_timeout_guard(db, normal_user, register_tool):
    class Clock:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            return self.t

    clock = Clock()

    def _slow(ctx, args, deps):
        clock.t += 10.0
        return {"output": {}, "evidence": []}

    register_tool("fake_slow", _slow)
    workflow_def = {"steps": [{"id": "s1", "tool": "fake_slow"}, {"id": "s2", "tool": "fake_slow", "inputs_from": ["s1"]}]}
    result = run_workflow(db, user=normal_user, manifest=_engine_manifest(), workflow_def=workflow_def, inputs={}, clock=clock)
    assert result.status == "failed"
    assert result.error["code"] == "SKILL_WORKFLOW_TIMEOUT"
    statuses = {record["id"]: record["status"] for record in result.steps}
    assert statuses == {"s1": "ok", "s2": "skipped"}


def test_engine_records_workflow_evidence_on_skill_run(db, normal_user, register_tool):
    calls: list[str] = []
    register_tool("fake_a", _ok_tool("fake_a", calls))
    skill_run = SimpleNamespace(id="run-1", evidence_json={})
    result = run_workflow(
        db,
        user=normal_user,
        manifest=_engine_manifest(),
        workflow_def={"steps": [{"id": "a", "tool": "fake_a"}]},
        inputs={},
        skill_run=skill_run,
    )
    workflow = skill_run.evidence_json["workflow"]
    assert workflow["status"] == result.status == "completed"
    assert workflow["steps"][0]["id"] == "a"
    assert workflow["evidence_refs"][0]["ref"] == "fake_a"
    assert workflow["output"] == result.output


def test_engine_blocks_policy_violations(db, normal_user, register_tool):
    register_tool("custom_internal", _ok_tool("custom_internal", []))
    # Policy tools must be in the manifest allowlist.
    result = run_workflow(
        db,
        user=normal_user,
        manifest=_engine_manifest(tool_allowlist=[]),
        workflow_def={"steps": [{"id": "a", "tool": "get_market_quote"}]},
        inputs={},
    )
    assert result.status == "failed"
    assert result.error["code"] == "SKILL_TOOL_DENIED"
    # Engine-internal tools are reserved for official workflows.
    result = run_workflow(
        db,
        user=normal_user,
        manifest=_engine_manifest(scope="personal"),
        workflow_def={"steps": [{"id": "a", "tool": "custom_internal"}]},
        inputs={},
    )
    assert result.status == "failed"
    assert result.error["code"] == "SKILL_TOOL_DENIED"


def test_workflow_definition_validation():
    with pytest.raises(WorkflowError) as missing:
        load_workflow_definition({}, "workflows/missing.yaml")
    assert missing.value.code == "SKILL_WORKFLOW_NOT_FOUND"
    with pytest.raises(WorkflowError) as unknown:
        load_workflow_definition({"workflows/x.yaml": "steps:\n  - {id: a, tool: no_such_tool}\n"}, "workflows/x.yaml")
    assert unknown.value.code == "SKILL_WORKFLOW_INVALID"
    with pytest.raises(WorkflowError) as cycle:
        load_workflow_definition(
            {"workflows/x.yaml": "steps:\n  - {id: a, tool: get_recent_news, inputs_from: [b]}\n  - {id: b, tool: get_recent_news, inputs_from: [a]}\n"},
            "workflows/x.yaml",
        )
    assert cycle.value.code == "SKILL_WORKFLOW_INVALID"
    assert "cycle" in str(cycle.value)


# ---------------------------------------------------------------------------
# Official workflow catalog
# ---------------------------------------------------------------------------


def test_seed_official_skills_is_idempotent(db):
    seed_official_skills(db)
    db.commit()
    seed_official_skills(db)
    db.commit()
    versions_before = db.query(SkillVersion).count()
    permissions_before = db.query(SkillPermission).count()
    seed_official_skills(db)
    db.commit()
    assert db.query(SkillVersion).count() == versions_before
    assert db.query(SkillPermission).count() == permissions_before
    slugs = {row.slug for row in db.query(Skill)}
    assert set(WORKFLOW_SLUGS) <= slugs
    for manifest, _ in WORKFLOW_BUILTIN_SKILLS:
        skill = db.get(Skill, manifest.skill_id)
        assert skill.scope == "official"
        assert skill.status == "published"
        assert skill.allow_autopilot is True
        assert skill.allow_order_intent is False
        assert skill.billing_type == "included"


@pytest.mark.parametrize("slug", WORKFLOW_SLUGS)
def test_workflow_skill_manifest_and_bundle_validate(db, normal_user, slug):
    resolved = _resolved(db, normal_user, slug)
    manifest = resolved.manifest
    assert manifest.scope == "official" and manifest.release_status == "published"
    assert manifest.evidence.require_source_timestamp and manifest.evidence.require_citation_links
    workflow_def = load_workflow_definition(resolved.version.content_bundle_json, manifest.workflow_template_ref)
    step_ids = {step["id"] for step in workflow_def["steps"]}
    for step in workflow_def["steps"]:
        assert step["tool"] in TOOL_REGISTRY
        assert set(step.get("inputs_from", [])) <= step_ids
        if step["tool"] in workflows.POLICY_TOOL_NAMES:
            assert step["tool"] in manifest.tool_allowlist
    for spec in (workflow_def.get("output") or {}).values():
        if isinstance(spec, dict) and "from" in spec:
            assert spec["from"] in step_ids
    assert db.query(SkillPermission).filter_by(skill_version_id=resolved.version.id).count() >= len(manifest.tool_allowlist)


def test_overnight_market_brief_contains_event_titles_and_citations(db, normal_user):
    _seed_healthy_snapshot(db)
    _seed_event(db, event_type="price_move", title="BTC up 6.2% in 24h", url="https://news.test/btc-move", kind="market_quote")
    _seed_event(db, event_type="news", title="ETF flows hit record", url="https://news.test/etf-flows", kind="news_document")
    resolved = _resolved(db, normal_user, "overnight_market_brief")
    run = invoke_workflow_skill(db, user=normal_user, slug="overnight_market_brief", inputs={"locale": "en"}, trigger_source="api")
    assert run.status == "completed"
    workflow = run.evidence_json["workflow"]
    assert workflow["status"] == "completed"
    output = workflow["output"]
    validate_json_instance(resolved.manifest.output_schema, output)
    assert "BTC up 6.2% in 24h" in output["brief_markdown"]
    assert "ETF flows hit record" in output["brief_markdown"]
    assert "https://news.test/btc-move" in output["brief_markdown"]
    assert "https://news.test/etf-flows" in output["brief_markdown"]
    assert len(output["events"]) == 2
    assert output["health"]["sources"]
    assert run.credits_reserved > 0 and run.credits_used == run.credits_reserved
    assert run.usage_json["steps_ok"] == 2

    zh_run = invoke_workflow_skill(db, user=normal_user, slug="overnight_market_brief", inputs={"locale": "zh"}, trigger_source="api")
    assert "隔夜市场简报" in _workflow_output(zh_run)["brief_markdown"]


def test_overnight_brief_marks_degraded_when_evidence_missing(db, normal_user):
    run = invoke_workflow_skill(db, user=normal_user, slug="overnight_market_brief", inputs={"locale": "en"}, trigger_source="api")
    assert run.status == "completed"  # terminal state; workflow itself degraded
    workflow = run.evidence_json["workflow"]
    assert workflow["status"] == "degraded"
    assert workflow["degraded_steps"] == ["compose"]
    compose = next(record for record in workflow["steps"] if record["id"] == "compose")
    assert compose["error"]["code"] == "INSUFFICIENT_EVIDENCE"
    assert "Evidence gaps" in workflow["output"]["brief_markdown"]


def test_portfolio_impact_review_with_connected_account(db, pro_user):
    _seed_healthy_snapshot(db)
    _connect_portfolio(db, pro_user)
    resolved = _resolved(db, pro_user, "portfolio_impact_review")
    run = invoke_workflow_skill(db, user=pro_user, slug="portfolio_impact_review", inputs={"locale": "en"}, trigger_source="api")
    assert run.status == "completed"
    output = _workflow_output(run)
    validate_json_instance(resolved.manifest.output_schema, output)
    assert output["nav"] == 1000.0
    assert output["impacts"] == []
    assert output["gaps"] == []
    assert "NAV" in output["review_markdown"]


def test_portfolio_impact_review_unconnected_is_honest(db, normal_user):
    resolved = _resolved(db, normal_user, "portfolio_impact_review")
    run = invoke_workflow_skill(db, user=normal_user, slug="portfolio_impact_review", inputs={"locale": "en"}, trigger_source="api")
    assert run.status == "completed"
    workflow = run.evidence_json["workflow"]
    assert workflow["status"] == "degraded"  # no portfolio evidence available
    output = workflow["output"]
    validate_json_instance(resolved.manifest.output_schema, output)
    assert output["nav"] is None
    assert any("portfolio" in gap.lower() for gap in output["gaps"])


def test_earnings_event_map_never_includes_estimated(db, normal_user):
    _seed_event(db, event_type="earnings_confirmed", title="BTC Corp earnings confirmed for 2026-07-27", url="https://nasdaq.test/earnings", kind="earnings_calendar", days_ahead=2)
    _seed_event(db, event_type="earnings_estimated", title="MSTR earnings (est.)", url="https://legacy.test/mstr-est", kind="earnings_estimate", days_ahead=3)
    db.add(Alert(user_id=normal_user.id, asset="BTC", message="watch", severity="low", channel="email", idempotency_key="watch-btc"))
    db.commit()
    resolved = _resolved(db, normal_user, "earnings_event_map")
    run = invoke_workflow_skill(db, user=normal_user, slug="earnings_event_map", inputs={"days": 14}, trigger_source="api")
    assert run.status == "completed"
    output = _workflow_output(run)
    validate_json_instance(resolved.manifest.output_schema, output)
    titles = [event["title"] for event in output["events"]]
    assert titles == ["BTC Corp earnings confirmed for 2026-07-27"]
    assert not any("(est.)" in title for title in titles)
    assert output["mapped_assets"] == ["BTC"]
    earnings_step = next(record for record in run.evidence_json["workflow"]["steps"] if record["id"] == "earnings")
    assert {entry["kind"] for entry in earnings_step["evidence_refs"]} == {"earnings_calendar"}


def test_long_gamma_scan_ranks_candidates_with_provenance(db, normal_user, mock_deribit):
    resolved = _resolved(db, normal_user, "long_gamma_scan")
    run = invoke_workflow_skill(db, user=normal_user, slug="long_gamma_scan", inputs={"currencies": ["BTC"], "limit": 5}, trigger_source="api")
    assert run.status == "completed"
    output = _workflow_output(run)
    validate_json_instance(resolved.manifest.output_schema, output)
    assert output["as_of"] == "2026-07-25T00:00:00+00:00"
    assert len(output["candidates"]) == 2
    candidate = output["candidates"][0]
    for field in ("expiry", "strike", "gamma", "theta", "spread_pct", "open_interest", "timestamp", "source"):
        assert candidate[field] is not None, field
    assert candidate["execution_enabled"] is False
    assert candidate["source"] == "deribit_public"
    assert candidate["rationale"]
    assert [item["rank"] for item in output["candidates"]] == [1, 2]


def test_opportunity_scan_merges_sources_with_provenance(db, pro_user, mock_deribit):
    _seed_event(db, event_type="price_move", title="BTC up 6.2% in 24h", url="https://news.test/btc-move", kind="market_quote")
    db.add(Signal(asset="BTC", signal_type="market_structure", direction="long_watch", confidence=0.7, risk_score=3, thesis="t", catalyst="c", invalidation="i", timeframe="2-10 days"))
    db.commit()
    resolved = _resolved(db, pro_user, "opportunity_scan")
    run = invoke_workflow_skill(db, user=pro_user, slug="opportunity_scan", inputs={"limit": 10}, trigger_source="api")
    assert run.status == "completed"
    output = _workflow_output(run)
    validate_json_instance(resolved.manifest.output_schema, output)
    types = {item["type"] for item in output["opportunities"]}
    assert {"long_gamma", "price_move", "signal"} <= types
    for item in output["opportunities"]:
        assert "source" in item["provenance"]
    sources = {entry["name"]: entry["status"] for entry in output["sources"]}
    assert sources == {"opportunities": "ok", "gamma": "ok", "signals": "ok"}


def test_strategy_backtest_returns_run_id(db, pro_user):
    resolved = _resolved(db, pro_user, "strategy_backtest")
    run = invoke_workflow_skill(
        db,
        user=pro_user,
        slug="strategy_backtest",
        inputs={"spec": {"name": "Workflow momentum", "assets": ["BTC"], "signal": "momentum"}, "window_days": 90},
        trigger_source="api",
    )
    assert run.status == "completed"
    output = _workflow_output(run)
    validate_json_instance(resolved.manifest.output_schema, output)
    assert output["run_id"]
    assert output["status"] == "completed"
    assert output["metrics"]
    backtest = db.get(BacktestRun, output["run_id"])
    assert backtest is not None
    assert (backtest.spec_json or {}).get("context_meta", {}).get("skill") == "strategy_backtest"


def test_strategy_backtest_degrades_when_service_unavailable(db, pro_user, monkeypatch):
    def _down(*args, **kwargs):
        raise RuntimeError("backtest datastore offline")

    monkeypatch.setattr("apps.api.services.unified_backtest_service.create_unified_run", _down)
    resolved = _resolved(db, pro_user, "strategy_backtest")
    run = invoke_workflow_skill(
        db,
        user=pro_user,
        slug="strategy_backtest",
        inputs={"spec": {"name": "Workflow momentum", "assets": ["BTC"]}},
        trigger_source="api",
    )
    assert run.status == "completed"  # terminal; workflow marked degraded
    workflow = run.evidence_json["workflow"]
    assert workflow["status"] == "degraded"
    assert workflow["degraded_steps"] == ["kickoff"]
    output = workflow["output"]
    validate_json_instance(resolved.manifest.output_schema, output)
    assert output["run_id"] is None
    assert output["status"] == "unavailable"
    assert output["metrics"] is None
    kickoff = next(record for record in workflow["steps"] if record["id"] == "kickoff")
    assert kickoff["error"]["code"] == "BACKTEST_SERVICE_UNAVAILABLE"


def test_strategy_backtest_rejects_invalid_spec(db, pro_user):
    run = invoke_workflow_skill(
        db,
        user=pro_user,
        slug="strategy_backtest",
        inputs={"spec": {"name": "x", "assets": ["DOGE"]}},
        trigger_source="api",
    )
    assert run.status == "failed"
    workflow = run.evidence_json["workflow"]
    validate_step = workflow["steps"][0]
    assert validate_step["error"]["code"] == "BACKTEST_SPEC_INVALID"
    assert run.credits_used == 0


def test_execution_monitor_read_only_ok_path(db, normal_user):
    resolved = _resolved(db, normal_user, "execution_monitor")
    run = invoke_workflow_skill(db, user=normal_user, slug="execution_monitor", inputs={}, trigger_source="api")
    assert run.status == "completed"
    output = _workflow_output(run)
    validate_json_instance(resolved.manifest.output_schema, output)
    assert output["status"] == "ok"
    assert output["findings"][0]["title"] == "No runtime, order, or risk anomalies detected"


def test_run_scheduled_workflow_convenience(db, normal_user, monkeypatch):
    monkeypatch.setattr(skill_workflow_service, "SessionLocal", lambda: db)
    result = skill_workflow_service.run_scheduled_workflow("overnight_market_brief", normal_user.id, {"locale": "en"})
    assert result["slug"] == "overnight_market_brief"
    assert result["status"] == "completed"
    assert result["run_id"]


def test_invocation_is_idempotent_per_invocation_id(db, normal_user):
    first = invoke_workflow_skill(db, user=normal_user, slug="overnight_market_brief", inputs={}, trigger_source="scheduled_job", invocation_id="test:idem:1")
    second = invoke_workflow_skill(db, user=normal_user, slug="overnight_market_brief", inputs={}, trigger_source="scheduled_job", invocation_id="test:idem:1")
    assert first.id == second.id
    assert db.query(SkillRun).filter_by(trigger_source="scheduled_job", user_id=normal_user.id).count() == 1


# ---------------------------------------------------------------------------
# (Portfolio Autopilot was removed from the product — its worker task, router
#  endpoints and UI card were cut on 2026-08-30. Scheduled skill invocation
#  paths are covered by the module-level tests above.)
# ---------------------------------------------------------------------------

