from __future__ import annotations

from datetime import datetime, timezone

from apps.api.services.agent_service import create_conversation, quote_agent_run, start_run
from packages.agents.chat.tools import ToolResult, ToolSource
from packages.agents.prompts import build_prompt_bundle
from packages.agents.runtime import plan_agent_request
from packages.data.evidence import EvidencePack, EvidenceRequirement
from packages.data.lexicon import understand_query
from packages.database.models import AgentMessage
from tests.conftest import auth_headers


def test_financial_lexicon_normalizes_multilingual_assets_and_intent():
    result = understand_query("分析比特币和 Ethereum 本周的市场趋势")

    assert result.assets == ("BTC", "ETH")
    assert result.intent == "market_research"
    assert result.horizon == "short_term"
    assert result.locale == "zh"


def test_runtime_auto_selects_skill_sources_and_evidence_contract():
    plan = plan_agent_request("What is driving the current BTC market?")

    assert plan.intent == "market_research"
    assert plan.skill_slugs == ("market_research",)
    assert plan.data_sources == ("market", "rss")
    assert plan.evidence_requirements == ("market_quote", "source_document")
    assert plan.clarification_recommended is False


def test_ambiguous_market_goal_recommends_one_clarification_without_defaulting_to_btc(db, normal_user):
    plan = plan_agent_request("How does the market look right now?")
    quote = quote_agent_run(db, normal_user, "How does the market look right now?", context={})

    assert plan.clarification_recommended is True
    assert plan.clarification_fields == ("asset",)
    assert quote["planned_tools"] == []
    assert quote["plan"]["auto_selected_skills"] is False


def test_skill_allowlist_applies_to_early_trading_plans(db, normal_user):
    from packages.agents.chat.tools import AgentToolRegistry

    calls = AgentToolRegistry(db, normal_user.id).plan(
        "Buy BTC now",
        skills=["market_research"],
        data_sources=["market", "rss"],
        skill_tool_allowlist={"get_market_quote", "search_source_documents"},
    )

    assert calls == []


def test_agent_quote_is_server_planned_and_persists_runtime_metadata(db, normal_user):
    quote = quote_agent_run(db, normal_user, "Assess current BTC market conditions", context={})

    assert quote["plan"]["intent"] == "market_research"
    assert quote["plan"]["auto_selected_skills"] is True
    assert quote["planned_tools"] == ["get_market_quote", "search_source_documents"]
    assert quote["task_type"] == "agent_market_research"
    assert quote["reservation_amount"] >= 2

    conversation = create_conversation(db, normal_user)
    run = start_run(db, normal_user, conversation, "Assess current BTC market conditions", context={})
    message = db.get(AgentMessage, run.user_message_id)
    assert message.context_json["runtime"]["intent"] == "market_research"
    assert message.context_json["runtime"]["prompt_refs"]
    assert message.context_json["skills"][0]["slug"] == "market_research"


def test_agent_quote_api_does_not_accept_client_task_type(api_client, normal_user):
    response = api_client.post(
        "/api/agent/quote",
        headers=auth_headers(normal_user),
        json={"content": "latest BTC news", "data_sources": [], "skill_refs": [], "model": "default"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_type"] == "agent_news_research"
    assert payload["plan"]["intent"] == "news_research"


def test_evidence_pack_reports_missing_and_sufficient_requirements():
    pack = EvidencePack([EvidenceRequirement("market_quote"), EvidenceRequirement("source_document")])
    pack.add_tool_result(ToolResult("get_market_quote", [{"symbol": "BTC", "provider": "binance"}], "quote"))
    assert pack.sufficient is False
    assert pack.missing == ["source_document"]

    pack.add_tool_result(ToolResult("search_source_documents", [{"title": "BTC update", "provider": "rss"}], "documents", [
        ToolSource("rss", "BTC update", "https://example.com/btc", None, None, datetime.now(timezone.utc))
    ]))
    assert pack.sufficient is True
    assert pack.public_summary()["source_count"] == 1


def test_prompt_registry_separates_behavior_from_skill_and_user_preferences():
    bundle = build_prompt_bundle(
        locale="zh",
        runtime_plan={"intent": "market_research"},
        skill_instructions="Require fresh market evidence.",
        response_preferences="先结论后证据",
        attachments_text="",
    )

    assert "DATA EVIDENCE RULES" in bundle.system_prompt
    assert "CONVERSATION EXPERIENCE" in bundle.system_prompt
    assert "SERVER-VALIDATED AGENT PLAN" in bundle.context_prompt
    assert "先结论后证据" in bundle.context_prompt
    assert {item["prompt_id"] for item in bundle.references} == {
        "platform_identity", "evidence_policy", "trading_boundary", "conversation_experience"
    }
