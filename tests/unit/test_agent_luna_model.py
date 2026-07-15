import pytest

from apps.api.config import Settings
from apps.api.dependencies import create_access_token
from apps.api.services import agent_service
from packages.agents.llm.mock_provider import MockLLMProvider
from packages.agents.llm.openai_provider import OpenAIProvider
from packages.agents.llm.provider_factory import get_agent_llm_provider
from packages.database.models import AgentMessage, AgentRun, CreditLedger, UsageEvent


def luna_settings(**overrides) -> Settings:
    values = {
        "openai_api_key": "server-side-test-key",
        "openai_luna_enabled": True,
        "openai_luna_model": "gpt-5.6-luna",
        "openai_luna_allowed_plans": ("Max", "Enterprise"),
        "openai_luna_timeout_seconds": 90,
        "agent_model": "existing-default-model",
        "llm_provider": "mock",
        "enable_mock_agent": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_luna_provider_is_explicit_and_does_not_replace_default():
    settings = luna_settings()

    default = get_agent_llm_provider("default", settings)
    luna = get_agent_llm_provider("gpt-5.6-luna", settings)

    assert isinstance(default, MockLLMProvider)
    assert isinstance(luna, OpenAIProvider)
    assert luna.model == "gpt-5.6-luna"
    assert luna.timeout_seconds == 90


def test_luna_requires_eligible_plan_before_charging(db, pro_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: luna_settings())
    conversation = agent_service.create_conversation(db, pro_user)
    starting_balance = pro_user.credit_balance

    with pytest.raises(agent_service.AgentModelPlanError, match="AGENT_MODEL_PLAN_REQUIRED"):
        agent_service.start_run(db, pro_user, conversation, "Deep market research", context={"model": "gpt-5.6-luna"})

    db.refresh(pro_user)
    assert pro_user.credit_balance == starting_balance
    assert db.query(CreditLedger).filter(CreditLedger.action == "agent_luna_research").count() == 0


def test_unavailable_luna_fails_before_charging(db, max_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: luna_settings(openai_luna_enabled=False))
    conversation = agent_service.create_conversation(db, max_user)
    starting_balance = max_user.credit_balance

    with pytest.raises(agent_service.AgentModelUnavailableError, match="AGENT_MODEL_UNAVAILABLE"):
        agent_service.start_run(db, max_user, conversation, "Deep market research", context={"model": "gpt-5.6-luna"})

    db.refresh(max_user)
    assert max_user.credit_balance == starting_balance


def test_luna_run_charges_and_records_actual_model(db, max_user, monkeypatch):
    settings = luna_settings()
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)
    fake = MockLLMProvider()
    fake.provider_name = "openai"
    fake.model = "gpt-5.6-luna"
    monkeypatch.setattr(agent_service, "get_agent_llm_provider", lambda selected_model=None: fake)
    conversation = agent_service.create_conversation(db, max_user)
    starting_balance = max_user.credit_balance

    run = agent_service.start_run(db, max_user, conversation, "Deep market research", context={"model": "gpt-5.6-luna"})
    events = list(agent_service.stream_run(db, max_user, run.id, "en"))

    db.refresh(max_user)
    db.refresh(run)
    assistant = db.get(AgentMessage, run.assistant_message_id)
    usage = db.query(UsageEvent).filter_by(idempotency_key=f"agent-run:{run.id}").one()
    ledger = db.query(CreditLedger).filter_by(idempotency_key=f"agent-charge:{run.id}").one()
    assert run.credit_cost == 6
    assert max_user.credit_balance == starting_balance - 6
    assert ledger.action == "agent_luna_research"
    assert run.model == "gpt-5.6-luna"
    assert assistant.model == "gpt-5.6-luna"
    assert usage.metadata_json["model"] == "gpt-5.6-luna"
    assert any('"model": "gpt-5.6-luna"' in event for event in events)
    assert any('"creditsUsed": 6' in event for event in events)
    serialized = agent_service.serialize_message(db, assistant)
    assert serialized["credits_used"] == 6
    assert serialized["credits_refunded"] is False


def test_luna_deep_research_uses_deep_metering_tier(db, max_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: luna_settings())
    conversation = agent_service.create_conversation(db, max_user)

    run = agent_service.start_run(
        db,
        max_user,
        conversation,
        "Run a deep market study",
        context={"model": "gpt-5.6-luna", "skills": ["deep_research"]},
    )

    ledger = db.query(CreditLedger).filter_by(idempotency_key=f"agent-charge:{run.id}").one()
    assert run.credit_cost == 20
    assert ledger.action == "luna_deep_research"


def test_capabilities_report_luna_plan_and_availability(db, normal_user, max_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: luna_settings())

    free_option = agent_service.agent_model_options(db, normal_user)[1]
    max_option = agent_service.agent_model_options(db, max_user)[1]

    assert free_option == {
        "id": "gpt-5.6-luna",
        "display_name": "GPT-5.6 Luna",
        "description": "High-quality deep market research for selective use.",
        "provider": "openai",
        "available": False,
        "reason": "plan_required",
        "credit_cost": None,
    }
    assert max_option["available"] is True
    assert max_option["reason"] is None


def test_api_rejects_forged_or_unentitled_model_selection(api_client, db, normal_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: luna_settings())
    headers = {"Authorization": f"Bearer {create_access_token(normal_user)}"}
    conversation_id = api_client.post("/api/agent/conversations", json={}, headers=headers).json()["conversation"]["id"]

    forged = api_client.post(f"/api/agent/conversations/{conversation_id}/messages", json={"content": "Research", "model": "forged-model"}, headers=headers)
    luna = api_client.post(f"/api/agent/conversations/{conversation_id}/messages", json={"content": "Research", "model": "gpt-5.6-luna"}, headers=headers)

    assert forged.status_code == 400
    assert forged.json()["detail"]["code"] == "AGENT_MODEL_INVALID"
    assert luna.status_code == 403
    assert luna.json()["detail"]["code"] == "AGENT_MODEL_PLAN_REQUIRED"
    assert db.query(AgentRun).filter_by(conversation_id=conversation_id).count() == 0
