"""Unit tests for the unified conversational answer service (P0-4)."""
from __future__ import annotations

import json

import pytest

from apps.api.routers import secretary
from apps.api.services import agent_answer_service
from packages.agents.llm.mock_provider import MockLLMProvider


@pytest.fixture(autouse=True)
def deterministic_llm_fallback(monkeypatch):
    """Keep the LLM-lite classifier fallback offline and deterministic."""
    monkeypatch.setattr(agent_answer_service, "get_llm_provider", lambda: MockLLMProvider())


class TestIntentClassifier:
    @pytest.mark.parametrize(
        "text",
        [
            "隔夜有什么重要的事？",
            "昨晚市场发生了什么？",
            "what happened overnight",
            "anything important last night?",
        ],
    )
    def test_overnight_brief(self, text):
        assert agent_answer_service.classify_intent(text) == "overnight_brief"

    @pytest.mark.parametrize(
        "text",
        [
            "我的投资组合怎么样？",
            "我的持仓现在如何？",
            "how is my portfolio",
            "how are my holdings doing",
        ],
    )
    def test_portfolio_review(self, text):
        assert agent_answer_service.classify_intent(text) == "portfolio_review"

    @pytest.mark.parametrize(
        "text",
        [
            "这次财报会影响我哪些资产？",
            "台积电业绩公布对我哪些持仓有影响？",
            "how will this earnings affect my assets",
            "does the FOMC event impact my portfolio",
        ],
    )
    def test_event_impact(self, text):
        assert agent_answer_service.classify_intent(text) == "event_impact"

    @pytest.mark.parametrize(
        "text",
        [
            "今天有什么长伽马机会？",
            "现在有哪些做多伽马的机会？",
            "any long gamma opportunities today",
            "run a gamma scan for me",
        ],
    )
    def test_long_gamma_scan(self, text):
        assert agent_answer_service.classify_intent(text) == "long_gamma_scan"

    @pytest.mark.parametrize(
        "text",
        [
            "What is the BTC market price?",
            "Help me plan today's research.",
            "Give me a full deep research report on SOL tokenomics",
            "帮我写一封给房东的邮件",
        ],
    )
    def test_unrelated_falls_through(self, text):
        assert agent_answer_service.classify_intent(text) is None

    def test_llm_fallback_strict_label_parsing(self, monkeypatch):
        class LabelProvider:
            def complete(self, *args, **kwargs):
                return "Portfolio_review."

        monkeypatch.setattr(agent_answer_service, "get_llm_provider", lambda: LabelProvider())
        assert agent_answer_service.classify_intent("something with no keywords at all") == "portfolio_review"

    def test_llm_fallback_noise_falls_through(self, monkeypatch):
        class NoiseProvider:
            def complete(self, *args, **kwargs):
                return "I am not sure, maybe portfolio_review or other"

        monkeypatch.setattr(agent_answer_service, "get_llm_provider", lambda: NoiseProvider())
        assert agent_answer_service.classify_intent("something with no keywords at all") is None

    def test_llm_fallback_failure_falls_through(self, monkeypatch):
        class FailingProvider:
            def complete(self, *args, **kwargs):
                raise RuntimeError("provider down")

        monkeypatch.setattr(agent_answer_service, "get_llm_provider", lambda: FailingProvider())
        assert agent_answer_service.classify_intent("something with no keywords at all") is None


class TestSecretarySharedFacts:
    def _canned_today(self):
        return {
            "as_of": "2026-07-25T00:00:00+00:00",
            "overnight_events": [
                {
                    "event_type": "news",
                    "title": "BTC rallies on stored test news",
                    "confidence": 0.9,
                    "source": {
                        "provider": "news:rss",
                        "url": "https://example.com/btc-rally",
                        "published_at": "2026-07-24T23:00:00+00:00",
                    },
                }
            ],
            "next_event": None,
            "health": {"overall": "ok", "sources": {}},
        }

    def test_verified_facts_block_uses_latest_snapshot(self, db, demo_user, monkeypatch):
        monkeypatch.setattr(
            agent_answer_service.research_event_service,
            "get_today",
            lambda db, user, locale="en": self._canned_today(),
        )
        block = agent_answer_service.verified_facts_block(db, demo_user, "en")
        assert "VERIFIED FACTS" in block
        assert "BTC rallies on stored test news" in block
        assert "https://example.com/btc-rally" in block

    def test_secretary_prompt_includes_verified_facts_block(self, db, demo_user, monkeypatch):
        monkeypatch.setattr(
            agent_answer_service.research_event_service,
            "get_today",
            lambda db, user, locale="en": self._canned_today(),
        )
        facts_context = agent_answer_service.shared_facts_context(db, demo_user, "en")
        prompt = secretary._prompt("en", [], "what happened today?", "", facts_context)
        assert "VERIFIED FACTS" in prompt
        assert "BTC rallies on stored test news" in prompt
        # demo user has no connected portfolio: the block must say so.
        assert "no portfolio is connected" in prompt
        # Persona is preserved.
        assert "private companion secretary" in prompt

    def test_verified_facts_block_marks_degraded_snapshot(self, db, demo_user, monkeypatch):
        canned = self._canned_today()
        canned["health"] = {"overall": "degraded", "sources": {}, "note": "no_research_snapshot"}
        canned["overnight_events"] = []
        monkeypatch.setattr(
            agent_answer_service.research_event_service,
            "get_today",
            lambda db, user, locale="en": canned,
        )
        block = agent_answer_service.verified_facts_block(db, demo_user, "en")
        assert "degraded" in block
        assert "No verified market events" in block


class TestEnvelope:
    def _facts(self):
        return {
            "as_of": "2026-07-25T00:00:00+00:00",
            "intent": "overnight_brief",
            "events": [
                {
                    "event_type": "news",
                    "title": "BTC rallies",
                    "confidence": 0.9,
                    "source": {"provider": "news:rss", "url": "https://example.com/a", "published_at": "2026-07-24T23:00:00+00:00"},
                }
            ],
            "upcoming": [],
            "opportunities": None,
            "portfolio": {"connected": False, "missing_data": ["No real portfolio account is connected"]},
            "portfolio_impacts": [],
            "actions": [],
            "next_event": None,
            "health": {"overall": "ok", "sources": {}},
            "evidence_gaps": [],
            "degraded": True,
            "_citations": [
                {"provider": "news:rss", "title": "BTC rallies", "url": "https://example.com/a", "published_at": "2026-07-24T23:00:00+00:00"}
            ],
        }

    def test_envelope_shape_and_disconnected_portfolio(self):
        envelope = agent_answer_service.build_envelope(self._facts(), reserved=12, settled=7)
        assert envelope["as_of"] == "2026-07-25T00:00:00+00:00"
        assert envelope["intent"] == "overnight_brief"
        assert envelope["portfolio_impact"] == {"connected": False}
        assert 0 <= envelope["confidence"] <= 1
        assert envelope["next_actions"]
        assert all({"action_type", "title"} <= set(action) for action in envelope["next_actions"])
        assert envelope["credits"] == {"reserved": 12, "settled": 7}
        assert envelope["degraded"] is True
        assert envelope["sources"] == [{"provider": "news:rss", "url": "https://example.com/a", "published_at": "2026-07-24T23:00:00+00:00"}]

    def test_envelope_contains_no_secret_material(self):
        envelope = agent_answer_service.build_envelope(self._facts(), reserved=12, settled=7)
        for source in envelope["sources"]:
            assert set(source) <= {"provider", "url", "published_at"}
        blob = json.dumps(envelope, ensure_ascii=False).lower()
        for marker in ("api_key", "apikey", "secret", "bearer", "token", "password"):
            assert marker not in blob
