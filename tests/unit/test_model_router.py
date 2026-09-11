from __future__ import annotations

import json
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from apps.api.config import (
    DEEPSEEK_MODEL_FLASH,
    Settings,
    normalize_deepseek_model,
    validate_production_settings,
)
from packages.agents.llm import model_router as router_module
from packages.agents.llm.deepseek_provider import DeepSeekProvider
from packages.agents.llm.kimi_provider import KimiProvider
from packages.agents.llm.mock_provider import MockLLMProvider
from packages.agents.llm.model_router import (
    KIMI_TASK_TYPES,
    LUNA_TASK_TYPES,
    ModelRouter,
    ModelRouterUnavailable,
)
from packages.agents.llm.provider_factory import get_llm_provider
from packages.agents.llm.schemas import ChatMessage, LLMResponse
from packages.database.models import LLMCallLog


def router_settings(**overrides) -> Settings:
    values = {
        "deepseek_api_key": "",
        "deepseek_model": "deepseek-flash",
        "openai_api_key": "",
        "openai_luna_enabled": True,
        "openai_luna_model": "gpt-5.6-luna",
        "openai_luna_allowed_plans": ("Max", "Enterprise"),
        "openai_luna_auto_route": False,
        "kimi_enabled": False,
        "kimi_api_key": "",
        "kimi_model": "kimi-k3",
        "kimi_base_url": "https://api.moonshot.ai/v1",
        "kimi_auto_route": False,
        "app_environment": "development",
    }
    values.update(overrides)
    return Settings(**values)


# ----------------------------------------------------------------------
# DeepSeek V4.1 Flash model identity
# ----------------------------------------------------------------------
def test_legacy_deepseek_names_resolve_to_the_model_that_serves_them():
    """Retired names must be recorded as the model that actually ran.

    DeepSeek still accepts ``deepseek-v4-flash`` but serves V4.1 Flash, so the
    effective id is the official ``deepseek-flash`` name.
    """
    assert normalize_deepseek_model("deepseek-v4-flash") == DEEPSEEK_MODEL_FLASH
    assert normalize_deepseek_model("deepseek-v4-flash-vision-exp") == DEEPSEEK_MODEL_FLASH
    assert normalize_deepseek_model("deepseek-flash") == DEEPSEEK_MODEL_FLASH
    # Unset falls back to the platform default.
    assert normalize_deepseek_model("") == DEEPSEEK_MODEL_FLASH
    assert normalize_deepseek_model(None) == DEEPSEEK_MODEL_FLASH


def test_explicitly_different_models_are_never_rewritten():
    """An explicitly chosen model must not be silently swapped for DeepSeek.

    ``deepseek-v4-pro`` is a genuinely different model until DeepSeek's
    scheduled 2026-09-14 cut-over, and any third-party id is the caller's
    choice. Rewriting either would falsify what actually served the request.
    """
    assert normalize_deepseek_model("deepseek-v4-pro") == "deepseek-v4-pro"
    assert normalize_deepseek_model("kimi-k3") == "kimi-k3"
    assert normalize_deepseek_model("gpt-5.6-luna") == "gpt-5.6-luna"


def test_settings_expose_effective_model_and_display_name():
    settings = router_settings(deepseek_model="deepseek-v4-flash")

    assert settings.deepseek_effective_model == DEEPSEEK_MODEL_FLASH
    assert settings.deepseek_display_name == "DeepSeek V4.1 Flash"


def test_default_deepseek_model_is_v41_flash_not_the_retired_name(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    assert Settings().deepseek_model == DEEPSEEK_MODEL_FLASH


def test_thinking_mode_is_off_by_default_and_opt_in():
    assert Settings().deepseek_thinking_enabled is False
    assert router_settings(deepseek_thinking_mode="enabled").deepseek_thinking_enabled is True
    # An effort outside DeepSeek's supported set falls back to `high`.
    assert router_settings(deepseek_reasoning_effort="ultra").deepseek_effective_reasoning_effort == "high"
    assert router_settings(deepseek_reasoning_effort="low").deepseek_effective_reasoning_effort == "low"


# ----------------------------------------------------------------------
# Routing table
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "task_type",
    [
        "agent_chat",
        "secretary_dialog",
        "default_chat",
        "daily_market_report",
        "classification",
        "summarization",
        "portfolio_risk_review",
        "strategy_review",
        "backtest_review",
        "luna_research",
        "agent_deep_research",
        "deep_research",
        "document_synthesis",
        "source_crosscheck",
        "kimi_research",
    ],
)
def test_every_automatic_task_defaults_to_deepseek_v41_flash(task_type):
    """All platform-owned automatic tasks run on DeepSeek V4.1 Flash."""
    route = ModelRouter(router_settings()).route_for_task(task_type)

    assert route.provider_name == "deepseek"
    assert route.model == DEEPSEEK_MODEL_FLASH


def test_kimi_and_luna_lanes_remain_opt_in():
    """Re-enabling the historical lanes restores them for their task types."""
    settings = router_settings(
        kimi_auto_route=True,
        kimi_enabled=True,
        kimi_api_key="test-only-kimi-key",
        openai_luna_auto_route=True,
        openai_api_key="test-only-openai-key",
    )
    router = ModelRouter(settings)

    assert router.route_for_task("deep_research").provider_name == "kimi"
    assert router.route_for_task("portfolio_risk_review").provider_name == "openai"
    # ...and a non-lane task still uses DeepSeek.
    assert router.route_for_task("agent_chat").provider_name == "deepseek"


def test_route_records_why_a_secondary_lane_was_skipped():
    disabled = ModelRouter(router_settings()).route_for_task("deep_research")
    unavailable = ModelRouter(
        router_settings(kimi_auto_route=True, kimi_enabled=False)
    ).route_for_task("deep_research")

    # An operator decision is not a degradation; a broken opt-in lane is.
    assert disabled.reason == "kimi_lane_consolidated_on_deepseek"
    assert unavailable.reason == "kimi_unavailable"


def test_route_for_unknown_task_defaults_to_deepseek():
    route = ModelRouter(router_settings()).route_for_task("never_seen_before")

    assert route.provider_name == "deepseek"
    assert route.reason == "default"


# ----------------------------------------------------------------------
# Kimi provider
# ----------------------------------------------------------------------
class _FakeCompletions:
    def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="kimi synthesis output"))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8),
        )


class _FakeOpenAIClient:
    def __init__(self, **kwargs):
        self.chat = SimpleNamespace(completions=_FakeCompletions())


def test_kimi_provider_chat_success_logs_call(db, demo_user, monkeypatch):
    fake_openai = SimpleNamespace(OpenAI=lambda **kwargs: _FakeOpenAIClient(**kwargs))
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    settings = router_settings(kimi_enabled=True, kimi_api_key="test-only-kimi-key")
    provider = KimiProvider(settings)

    assert provider.provider_name == "kimi"
    assert provider.configured is True

    response = provider.chat(
        [ChatMessage(role="user", content="Summarize the evidence pack")],
        task_type="kimi_research",
        locale="zh",
        user_id=demo_user.id,
        db=db,
    )
    db.commit()
    log = db.query(LLMCallLog).order_by(LLMCallLog.created_at.desc()).first()

    assert response.content == "kimi synthesis output"
    assert response.provider == "kimi"
    assert response.model == "kimi-k3"
    assert log.provider == "kimi"
    assert log.model == "kimi-k3"
    assert log.task_type == "kimi_research"
    assert log.status == "success"
    assert log.prompt_tokens == 12
    assert log.completion_tokens == 8


def test_kimi_provider_not_configured_without_enable_or_key():
    disabled = KimiProvider(router_settings(kimi_enabled=False, kimi_api_key="test-only-kimi-key"))
    no_key = KimiProvider(router_settings(kimi_enabled=True, kimi_api_key=""))

    assert disabled.configured is False
    assert disabled.last_error == "KIMI_ENABLED is false"
    assert no_key.configured is False
    assert no_key.last_error == "KIMI_API_KEY is not configured"


def test_factory_kimi_unconfigured_falls_back_to_mock_like_other_providers():
    settings = router_settings(llm_provider="kimi", kimi_enabled=True, kimi_api_key="")

    provider = get_llm_provider(settings)

    assert isinstance(provider, MockLLMProvider)
    assert provider.last_error == "KIMI_API_KEY is not configured"


# ----------------------------------------------------------------------
# Router degradation
# ----------------------------------------------------------------------
def _fake_deepseek_chat(self, messages, *, task_type, locale="en", user_id=None, db=None, response_format=None):
    return LLMResponse(
        content="deepseek answer",
        provider=self.provider_name,
        model=self.model,
        prompt_tokens=5,
        completion_tokens=3,
        total_tokens=8,
    )


def test_router_runs_deepseek_directly_for_research_by_default(db, demo_user, monkeypatch):
    """With the Kimi lane off, research goes straight to DeepSeek with no fallback noise."""
    monkeypatch.setattr(DeepSeekProvider, "chat", _fake_deepseek_chat)
    settings = router_settings(deepseek_api_key="test-only-deepseek-key")
    router = ModelRouter(settings)

    response = router.complete(
        [ChatMessage(role="user", content="run deep research")],
        task_type="deep_research",
        locale="en",
        user_id=demo_user.id,
        db=db,
    )
    db.commit()
    log = db.query(LLMCallLog).order_by(LLMCallLog.created_at.desc()).first()

    assert response.provider == "deepseek"
    assert response.model == DEEPSEEK_MODEL_FLASH
    # No degradation: DeepSeek is the intended route, not a fallback. The route
    # reason records that the historical Kimi lane no longer owns this task.
    assert "degraded" not in response.metadata
    assert response.metadata["route_reason"] == "kimi_lane_consolidated_on_deepseek"
    assert log.provider == "deepseek"
    assert log.model == DEEPSEEK_MODEL_FLASH
    assert log.status == "success"
    assert log.latency_ms is not None


def test_router_degrades_to_deepseek_when_an_opt_in_kimi_lane_fails(db, demo_user, monkeypatch):
    """A re-enabled Kimi lane that cannot be reached degrades to DeepSeek and says so."""
    monkeypatch.setattr(DeepSeekProvider, "chat", _fake_deepseek_chat)
    settings = router_settings(
        deepseek_api_key="test-only-deepseek-key",
        kimi_auto_route=True,
        kimi_enabled=True,
        kimi_api_key="",
    )
    router = ModelRouter(settings)

    response = router.complete(
        [ChatMessage(role="user", content="run deep research")],
        task_type="deep_research",
        locale="en",
        user_id=demo_user.id,
        db=db,
    )
    db.commit()
    log = db.query(LLMCallLog).order_by(LLMCallLog.created_at.desc()).first()

    assert response.provider == "deepseek"
    assert response.metadata["degraded"] is True
    assert response.metadata["requested_provider"] == "kimi"
    assert response.metadata["route_reason"] == "kimi_unavailable"
    # The reason names the lane that was preferred but could not serve the
    # request, alongside the other providers' own misconfiguration.
    assert "kimi preferred but unavailable" in response.metadata["reason"]
    assert any(
        "openai not configured" in item
        for item in response.metadata["unavailable_fallbacks"]
    )
    assert log.provider == "deepseek"
    assert log.status == "success"
    assert log.latency_ms is not None


def test_router_raises_and_never_uses_mock_in_production(monkeypatch):
    settings = router_settings(app_environment="production")
    router = ModelRouter(settings)

    def _forbidden_mock_chat(self, *args, **kwargs):
        raise AssertionError("MockLLMProvider must never be returned in production")

    monkeypatch.setattr(MockLLMProvider, "chat", _forbidden_mock_chat)

    with pytest.raises(ModelRouterUnavailable, match="NO_PROVIDER_CONFIGURED"):
        router.complete([ChatMessage(role="user", content="hi")], task_type="agent_chat", db=None)


def test_router_uses_mock_only_outside_production_when_no_provider_configured():
    settings = router_settings(app_environment="development")
    router = ModelRouter(settings)

    response = router.complete([ChatMessage(role="user", content="hi")], task_type="agent_chat", db=None)

    assert response.provider == "mock"
    assert response.metadata["degraded"] is True
    assert response.metadata["requested_provider"] == "deepseek"
    assert response.metadata["reason"] == "no_real_provider_configured"


# ----------------------------------------------------------------------
# deep_research orchestration
# ----------------------------------------------------------------------
class _FakeProvider:
    def __init__(self, provider_name, model, *, content="", error=None, configured=True):
        self.provider_name = provider_name
        self.model = model
        self.content = content
        self.error = error
        self.configured = configured
        self.last_error = None if configured else "not configured"


def _install_deep_research_fakes(monkeypatch, *, luna_error=None):
    calls: list[tuple[str, str]] = []
    logged: list[dict] = []

    def _chat(self, messages, *, task_type, locale="en", user_id=None, db=None, response_format=None):
        calls.append((self.provider_name, task_type))
        if self.error is not None:
            raise self.error
        return LLMResponse(
            content=self.content,
            provider=self.provider_name,
            model=self.model,
            prompt_tokens=10,
            completion_tokens=6,
            total_tokens=16,
        )

    _FakeProvider.chat = _chat
    kimi = _FakeProvider("kimi", "kimi-k3", content='{"synthesis": "kimi synth", "agreements": ["rates drive both"], "contradictions": ["kimi cites growth, sources cite recession"]}')
    luna = _FakeProvider("openai", "gpt-5.6-luna", content="luna counter-review", error=luna_error)
    deepseek = _FakeProvider("deepseek", DEEPSEEK_MODEL_FLASH, content="final merged conclusion")

    monkeypatch.setattr(ModelRouter, "_kimi_provider", lambda self: kimi)
    monkeypatch.setattr(ModelRouter, "_luna_provider", lambda self, plan=None: luna)
    monkeypatch.setattr(ModelRouter, "_deepseek_provider", lambda self: deepseek)
    monkeypatch.setattr(router_module, "log_llm_call", lambda db, **kwargs: logged.append(kwargs))
    return calls, logged


def _full_pipeline_settings(**overrides) -> Settings:
    """Settings with both historical lanes explicitly re-enabled."""
    values = {
        "kimi_auto_route": True,
        "kimi_enabled": True,
        "kimi_api_key": "test-only-kimi-key",
        "openai_luna_auto_route": True,
        "openai_api_key": "test-only-openai-key",
    }
    values.update(overrides)
    return router_settings(**values)


def test_deep_research_flow_orders_models_and_surfaces_disagreements(monkeypatch):
    calls, logged = _install_deep_research_fakes(monkeypatch)
    router = ModelRouter(_full_pipeline_settings())

    result = router.deep_research(
        {"summary": "BTC evidence", "evidence_refs": ["ref-1", "ref-2"]},
        locale="en",
        user_id=None,
        db=None,
        plan="Max",
    )

    assert calls == [
        ("kimi", "deep_research_kimi_synthesis"),
        ("openai", "deep_research_luna_review"),
        ("deepseek", "deep_research_final_synthesis"),
    ]
    assert result["conclusion"] == "final merged conclusion"
    assert result["disagreements"] == ["kimi cites growth, sources cite recession"]
    assert result["evidence_refs"] == ["ref-1", "ref-2"]
    assert result["degraded"] is False
    assert result["skipped_models"] == []
    assert [trace["task_type"] for trace in result["model_traces"]] == [
        "deep_research_kimi_synthesis",
        "deep_research_luna_review",
        "deep_research_final_synthesis",
    ]
    assert all(trace["status"] == "success" for trace in result["model_traces"])
    assert all(trace["latency_ms"] is not None for trace in result["model_traces"])
    assert len(logged) == 3
    assert all(entry["latency_ms"] is not None for entry in logged)


def test_deep_research_records_skipped_model_when_luna_fails(monkeypatch):
    calls, logged = _install_deep_research_fakes(monkeypatch, luna_error=RuntimeError("luna boom"))
    router = ModelRouter(_full_pipeline_settings())

    result = router.deep_research({"summary": "BTC evidence"}, locale="en", user_id=None, db=None, plan="Max")

    assert calls == [
        ("kimi", "deep_research_kimi_synthesis"),
        ("openai", "deep_research_luna_review"),
        ("deepseek", "deep_research_final_synthesis"),
    ]
    assert result["conclusion"] == "final merged conclusion"
    assert result["degraded"] is True
    assert len(result["skipped_models"]) == 1
    skipped = result["skipped_models"][0]
    assert skipped["provider"] == "openai"
    assert skipped["task_type"] == "deep_research_luna_review"
    assert "luna boom" in skipped["reason"]
    luna_trace = next(trace for trace in result["model_traces"] if trace["task_type"] == "deep_research_luna_review")
    assert luna_trace["status"] == "failed"
    failed_logs = [entry for entry in logged if entry["status"] == "failed"]
    assert len(failed_logs) == 1
    assert failed_logs[0]["latency_ms"] is not None


def test_deep_research_skips_kimi_when_unconfigured(monkeypatch):
    calls, logged = _install_deep_research_fakes(monkeypatch)
    monkeypatch.setattr(ModelRouter, "_kimi_provider", lambda self: _FakeProvider("kimi", "kimi-k3", configured=False))
    router = ModelRouter(_full_pipeline_settings())

    result = router.deep_research({"summary": "BTC evidence"}, locale="en", user_id=None, db=None, plan="Max")

    assert ("kimi", "deep_research_kimi_synthesis") not in calls
    assert result["conclusion"] == "final merged conclusion"
    assert result["disagreements"] == []
    assert result["degraded"] is True
    assert any(item["provider"] == "kimi" for item in result["skipped_models"])


def test_deep_research_default_runs_single_deepseek_synthesis(monkeypatch):
    """The default pipeline is one DeepSeek V4.1 Flash call and records the skipped lanes."""
    calls, logged = _install_deep_research_fakes(monkeypatch)
    router = ModelRouter(router_settings())

    result = router.deep_research({"summary": "BTC evidence"}, locale="en", user_id=None, db=None, plan="Max")

    assert calls == [("deepseek", "deep_research_final_synthesis")]
    assert result["conclusion"] == "final merged conclusion"
    # Skipped lanes are still reported, with the reason, so the artifact is honest
    # about what was and was not exercised.
    reasons = {item["provider"]: item["reason"] for item in result["skipped_models"]}
    assert reasons["kimi"] == "kimi_lane_consolidated_on_deepseek"
    assert reasons["openai"] == "luna_lane_consolidated_on_deepseek"
    assert result["degraded"] is True
    # Only the model that actually ran is billed.
    assert len(logged) == 1
    assert logged[0]["model"] == DEEPSEEK_MODEL_FLASH


# ----------------------------------------------------------------------
# Status surface
# ----------------------------------------------------------------------
def test_router_status_reports_hosts_without_leaking_keys():
    settings = router_settings(
        deepseek_api_key="ds-secret",
        openai_api_key="oa-secret",
        kimi_enabled=True,
        kimi_api_key="kimi-secret",
    )

    status = ModelRouter(settings).router_status()

    assert status["providers"]["kimi"]["configured"] is True
    assert status["providers"]["kimi"]["enabled"] is True
    assert status["providers"]["kimi"]["base_url_host_only"] == "api.moonshot.ai"
    assert status["providers"]["deepseek"]["base_url_host_only"] == "api.deepseek.com"
    assert status["providers"]["deepseek"]["model"] == DEEPSEEK_MODEL_FLASH
    assert status["providers"]["openai"]["model"] == "gpt-5.6-luna"
    serialized = json.dumps(status)
    assert "ds-secret" not in serialized
    assert "oa-secret" not in serialized
    assert "kimi-secret" not in serialized


def test_router_status_separates_every_task_from_secondary_lane_ownership():
    default_status = ModelRouter(router_settings()).router_status()
    opt_in_status = ModelRouter(_full_pipeline_settings()).router_status()

    # Every automatic task is owned by DeepSeek; the secondary lanes own nothing
    # unless the operator re-enables them.
    assert default_status["routing"]["openai"] == []
    assert default_status["routing"]["kimi"] == []
    assert set(default_status["routing"]["deepseek"]) >= {
        "agent_chat",
        "daily_market_report",
        "deep_research",
        "portfolio_risk_review",
    }
    assert opt_in_status["routing"]["kimi"] == sorted(KIMI_TASK_TYPES)
    assert opt_in_status["routing"]["openai"] == sorted(LUNA_TASK_TYPES)


# ----------------------------------------------------------------------
# Production configuration guard
# ----------------------------------------------------------------------
def _valid_production_settings() -> Settings:
    return Settings(
        app_environment="production",
        database_url="postgresql+psycopg://puregamma:secret@postgres/puregamma",
        redis_url="redis://redis:6379/0",
        jwt_secret="j" * 32,
        session_secret="s" * 32,
        encryption_master_key="e" * 32,
        internal_runtime_secret="i" * 32,
        nautilus_runtime_secret="n" * 32,
        site_url="https://app.puregamma.ai",
        cors_origins=("https://app.puregamma.ai",),
        session_cookie_domain=".puregamma.ai",
        billing_mode="stripe",
        stripe_secret_key="sk_live_test",
        stripe_webhook_secret="whsec_test",
        stripe_success_url="https://app.puregamma.ai/billing/success",
        stripe_cancel_url="https://app.puregamma.ai/billing/cancel",
        google_oauth_redirect_uri="https://app.puregamma.ai/zh/auth/google/callback",
        mobile_google_oauth_redirect_uri="https://api.puregamma.ai/auth/mobile/google/callback",
        mobile_ibkr_oauth_redirect_uri="https://api.puregamma.ai/portfolio/ibkr/mobile/callback",
        llm_provider="deepseek",
        deepseek_api_key="server-only-key",
        openai_luna_enabled=False,
        kimi_enabled=False,
        imessage_provider="disabled",
        nautilus_execution_mode="paper",
        enable_mock_market_data=False,
    )


def test_production_guard_requires_kimi_key_and_model_when_enabled():
    with pytest.raises(RuntimeError, match="KIMI_API_KEY"):
        validate_production_settings(replace(_valid_production_settings(), kimi_enabled=True, kimi_api_key=""))

    with pytest.raises(RuntimeError, match="KIMI_MODEL"):
        validate_production_settings(replace(_valid_production_settings(), kimi_enabled=True, kimi_api_key="server-only-kimi-key", kimi_model=""))


def test_production_guard_accepts_configured_kimi():
    validate_production_settings(
        replace(_valid_production_settings(), kimi_enabled=True, kimi_api_key="server-only-kimi-key", kimi_model="kimi-k3")
    )
