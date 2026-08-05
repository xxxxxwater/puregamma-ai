from __future__ import annotations

import json
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from apps.api.config import Settings, validate_production_settings
from packages.agents.llm import model_router as router_module
from packages.agents.llm.deepseek_provider import DeepSeekProvider
from packages.agents.llm.kimi_provider import KimiProvider
from packages.agents.llm.mock_provider import MockLLMProvider
from packages.agents.llm.model_router import ModelRouter, ModelRouterUnavailable
from packages.agents.llm.provider_factory import get_llm_provider
from packages.agents.llm.schemas import ChatMessage, LLMResponse
from packages.database.models import LLMCallLog


def router_settings(**overrides) -> Settings:
    values = {
        "deepseek_api_key": "",
        "deepseek_model": "deepseek-v4-flash",
        "openai_api_key": "",
        "openai_luna_enabled": True,
        "openai_luna_model": "gpt-5.6-luna",
        "openai_luna_allowed_plans": ("Max", "Enterprise"),
        "kimi_enabled": False,
        "kimi_api_key": "",
        "kimi_model": "kimi-k3",
        "kimi_base_url": "https://api.moonshot.ai/v1",
        "app_environment": "development",
    }
    values.update(overrides)
    return Settings(**values)


# ----------------------------------------------------------------------
# Routing table
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("task_type", "provider"),
    [
        ("agent_chat", "deepseek"),
        ("secretary_dialog", "deepseek"),
        ("default_chat", "deepseek"),
        ("daily_market_report", "deepseek"),
        ("classification", "deepseek"),
        ("summarization", "deepseek"),
        ("portfolio_risk_review", "openai"),
        ("strategy_review", "openai"),
        ("backtest_review", "openai"),
        ("luna_research", "openai"),
        ("agent_deep_research", "kimi"),
        ("deep_research", "kimi"),
        ("document_synthesis", "kimi"),
        ("source_crosscheck", "kimi"),
        ("kimi_research", "kimi"),
    ],
)
def test_route_for_task_maps_documented_task_types(task_type, provider):
    route = ModelRouter(router_settings()).route_for_task(task_type)

    assert route.provider_name == provider


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


def test_router_degrades_to_deepseek_when_kimi_unconfigured(db, demo_user, monkeypatch):
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
    assert response.metadata["degraded"] is True
    assert response.metadata["requested_provider"] == "kimi"
    assert "kimi not configured" in response.metadata["reason"]
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
    deepseek = _FakeProvider("deepseek", "deepseek-v4-flash", content="final merged conclusion")

    monkeypatch.setattr(ModelRouter, "_kimi_provider", lambda self: kimi)
    monkeypatch.setattr(ModelRouter, "_luna_provider", lambda self, plan=None: luna)
    monkeypatch.setattr(ModelRouter, "_deepseek_provider", lambda self: deepseek)
    monkeypatch.setattr(router_module, "log_llm_call", lambda db, **kwargs: logged.append(kwargs))
    return calls, logged


def test_deep_research_flow_orders_models_and_surfaces_disagreements(monkeypatch):
    calls, logged = _install_deep_research_fakes(monkeypatch)
    router = ModelRouter(router_settings())

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
    router = ModelRouter(router_settings())

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
    router = ModelRouter(router_settings())

    result = router.deep_research({"summary": "BTC evidence"}, locale="en", user_id=None, db=None, plan="Max")

    assert ("kimi", "deep_research_kimi_synthesis") not in calls
    assert result["conclusion"] == "final merged conclusion"
    assert result["disagreements"] == []
    assert result["degraded"] is True
    assert any(item["provider"] == "kimi" for item in result["skipped_models"])


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
    assert status["providers"]["openai"]["model"] == "gpt-5.6-luna"
    serialized = json.dumps(status)
    assert "ds-secret" not in serialized
    assert "oa-secret" not in serialized
    assert "kimi-secret" not in serialized


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
