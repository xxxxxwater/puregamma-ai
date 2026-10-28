"""Every selectable Agent model is billed from an explicit rate, or refused.

A model the selector lists without a Credit rate used to be quoted, reserved
and settled at the platform default rate. These tests pin the fail-closed
rule and that the menu's estimate comes from the same rates and formula as
billing.
"""
from __future__ import annotations

import pytest

from apps.api.config import Settings
from apps.api.dependencies import create_access_token
from apps.api.services import agent_service
from packages.billing import metering
from packages.billing.metering import (
    MODEL_RATES,
    TYPICAL_TURN_HIGH,
    TYPICAL_TURN_LOW,
    ModelPricingNotConfigured,
    explicit_model_rate,
    parse_model_rates,
    quote_credits,
)
from packages.database.models import AgentRun, CreditLedger


def pricing_settings(**overrides) -> Settings:
    values = {
        "openai_api_key": "server-side-test-key",
        "openai_luna_enabled": True,
        "openai_agent_models": (("gpt-5.6-luna", "GPT-5.6 Luna"), ("gpt-6-sol", "GPT-6 Sol")),
        "openai_luna_allowed_plans": ("Max", "Enterprise"),
        "agent_model": "existing-default-model",
        "agent_model_credit_rates": "",
        "llm_provider": "mock",
        "enable_mock_agent": True,
    }
    values.update(overrides)
    return Settings(**values)


def options_by_id(db, user) -> dict[str, dict]:
    return {item["id"]: item for item in agent_service.agent_model_options(db, user)}


def test_rate_configuration_is_parsed_strictly():
    assert parse_model_rates("gpt-6-sol=2/0.8/2.5, GPT-6-Astra=3/1/3") == {
        "gpt-6-sol": (2.0, 0.8, 2.5),
        "gpt-6-astra": (3.0, 1.0, 3.0),
    }
    # Malformed or negative entries leave the model unpriced (refused), never guessed.
    assert parse_model_rates("gpt-6-sol=2/0.8,gpt-6-luna=-1/1/1,x=a/b/c,=1/1/1,nan=nan/1/1") == {}
    assert parse_model_rates("") == {}


def test_strict_quote_refuses_a_model_without_an_explicit_rate():
    with pytest.raises(ModelPricingNotConfigured):
        quote_credits(task_type="agent_luna_research", requested_model="gpt-6-sol", resolved_model="gpt-6-sol", strict_model_rate=True)
    # The same request priced explicitly uses that rate, not the default one.
    priced = quote_credits(
        task_type="agent_luna_research", requested_model="gpt-6-sol", resolved_model="gpt-6-sol",
        input_tokens=10_000, output_tokens=10_000, strict_model_rate=True,
        model_rates={"gpt-6-sol": (3.0, 1.0, 4.0)},
    )
    assert priced.credits == 3 + 10 + 40


def test_strict_quote_prices_by_selection_even_when_the_provider_echoes_a_snapshot_name():
    selected = quote_credits(task_type="agent_luna_research", requested_model="gpt-5.6-luna", resolved_model="gpt-5.6-luna-2026-09-14",
                             input_tokens=10_000, output_tokens=10_000, strict_model_rate=True)
    rate = MODEL_RATES["gpt-5.6-luna"]
    assert selected.credits == round(rate[0] + rate[1] * 10 + rate[2] * 10)


def test_unpriced_models_are_reported_unavailable_with_a_pricing_reason(db, max_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: pricing_settings())

    options = options_by_id(db, max_user)

    assert options["gpt-6-sol"]["available"] is False
    assert options["gpt-6-sol"]["reason"] == "pricing_not_configured"
    assert options["gpt-6-sol"]["estimate"] is None
    assert options["gpt-5.6-luna"]["available"] is True
    assert options["gpt-5.6-luna"]["estimate"]["min"] >= 1


def test_pricing_reason_wins_over_the_plan_reason(db, normal_user, monkeypatch):
    # An upgrade would not make an unpriced model runnable, so do not say it would.
    monkeypatch.setattr(agent_service, "get_settings", lambda: pricing_settings())

    options = options_by_id(db, normal_user)

    assert options["gpt-6-sol"]["reason"] == "pricing_not_configured"
    assert options["gpt-5.6-luna"]["reason"] == "plan_required"  # plan gating unchanged


def test_configured_rate_makes_the_model_available(db, max_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: pricing_settings(agent_model_credit_rates="gpt-6-sol=3/1/4"))

    option = options_by_id(db, max_user)["gpt-6-sol"]

    assert option["available"] is True
    assert option["reason"] is None


def test_quote_and_start_refuse_an_unpriced_model_before_charging(db, max_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: pricing_settings())
    conversation = agent_service.create_conversation(db, max_user)
    starting_balance = max_user.credit_balance

    with pytest.raises(agent_service.AgentModelPricingError, match="AGENT_MODEL_PRICING_NOT_CONFIGURED"):
        agent_service.quote_agent_run(db, max_user, "Deep market research", context={"model": "gpt-6-sol"})
    with pytest.raises(agent_service.AgentModelPricingError, match="AGENT_MODEL_PRICING_NOT_CONFIGURED"):
        agent_service.start_run(db, max_user, conversation, "Deep market research", context={"model": "gpt-6-sol"})

    db.refresh(max_user)
    assert max_user.credit_balance == starting_balance
    assert db.query(AgentRun).filter_by(conversation_id=conversation.id).count() == 0


def test_http_quote_message_and_billing_quote_refuse_an_unpriced_model(api_client, db, max_user, monkeypatch):
    settings = pricing_settings()
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)
    monkeypatch.setattr("apps.api.routers.billing.get_settings", lambda: settings)
    headers = {"Authorization": f"Bearer {create_access_token(max_user)}"}
    conversation_id = api_client.post("/api/agent/conversations", json={}, headers=headers).json()["conversation"]["id"]

    quote = api_client.post("/api/agent/quote", json={"content": "Research", "model": "gpt-6-sol"}, headers=headers)
    message = api_client.post(f"/api/agent/conversations/{conversation_id}/messages", json={"content": "Research", "model": "gpt-6-sol"}, headers=headers)
    billing = api_client.post("/billing/quote", json={"task_type": "luna_research", "requested_model": "gpt-6-sol"}, headers=headers)

    for response in (quote, message, billing):
        assert response.status_code == 503, response.text
        assert response.json()["detail"]["code"] == "AGENT_MODEL_PRICING_NOT_CONFIGURED"
    assert db.query(CreditLedger).filter(CreditLedger.user_id == max_user.id, CreditLedger.credits_delta < 0).count() == 0


def test_menu_estimate_equals_billing_for_the_typical_turn(db, max_user, monkeypatch):
    settings = pricing_settings(agent_model_credit_rates="gpt-6-sol=3/1/4")
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)

    options = options_by_id(db, max_user)

    for identifier in ("gpt-5.6-luna", "gpt-6-sol"):
        estimate = options[identifier]["estimate"]
        rates = settings.agent_model_rates
        expected = [
            quote_credits(task_type=estimate["task_type"], requested_model=identifier, resolved_model=identifier,
                          model_rates=rates, strict_model_rate=True, **turn).credits
            for turn in (TYPICAL_TURN_LOW, TYPICAL_TURN_HIGH)
        ]
        assert [estimate["min"], estimate["max"]] == expected
        assert explicit_model_rate(identifier, rates) is not None
    default = options["default"]["estimate"]
    assert default["min"] == quote_credits(task_type="agent_chat_basic", requested_model="default", resolved_model="existing-default-model", **TYPICAL_TURN_LOW).credits


def test_a_started_run_reserves_exactly_what_the_quote_said(db, max_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: pricing_settings(agent_model_credit_rates="gpt-6-sol=30/1/4"))
    conversation = agent_service.create_conversation(db, max_user)

    quote = agent_service.quote_agent_run(db, max_user, "Deep market research", context={"model": "gpt-6-sol"})
    run = agent_service.start_run(db, max_user, conversation, "Deep market research", context={"model": "gpt-6-sol"})

    # 30 base credits is above the default-rate quote, so this proves the configured rate was used.
    assert quote["reservation_amount"] == run.credit_cost >= 30


def test_capabilities_report_provider_capabilities_and_limits(api_client, db, max_user, monkeypatch):
    monkeypatch.setattr(agent_service, "get_settings", lambda: pricing_settings())
    headers = {"Authorization": f"Bearer {create_access_token(max_user)}"}

    models = {item["id"]: item for item in api_client.get("/api/agent/capabilities", headers=headers).json()["models"]}

    luna = models["gpt-5.6-luna"]
    assert luna["provider"] == "openai"
    assert luna["capabilities"]["chat"] is True
    assert luna["limits"] == {"plans": ["Max", "Enterprise"], "plan_allowed": True, "image_input": False}
    assert luna["estimate"]["unit"] == "credits" and luna["estimate"]["basis"] == "typical_turn"
    assert models["default"]["estimate"]["min"] <= models["default"]["estimate"]["max"]
    assert models["gpt-6-sol"]["reason"] == "pricing_not_configured"


def test_settlement_keeps_the_reserved_amount_if_the_rate_disappears_mid_run(db, max_user, monkeypatch):
    settings = {"value": pricing_settings(agent_model_credit_rates="gpt-6-sol=3/1/4")}
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings["value"])
    conversation = agent_service.create_conversation(db, max_user)
    run = agent_service.start_run(db, max_user, conversation, "Deep market research", context={"model": "gpt-6-sol"})
    reserved = run.credit_cost
    settings["value"] = pricing_settings()  # rate removed while the run is in flight

    user_message = db.get(agent_service.AgentMessage, run.user_message_id)
    settlement = agent_service._settle_agent_run(db, max_user, run, user_message, response_model="gpt-6-sol", prompt_tokens=50_000, completion_tokens=50_000, reason="completed")

    assert settlement.actual == reserved


def test_the_shipped_gpt6_defaults_are_not_priced_in_code():
    # The GPT-6 line is offered by default but has no product-approved rate in
    # code; it must be configured (AGENT_MODEL_CREDIT_RATES) before it is offered.
    for identifier in ("gpt-6-luna", "gpt-6-sol", "gpt-6-astra"):
        assert identifier not in metering.MODEL_RATES
