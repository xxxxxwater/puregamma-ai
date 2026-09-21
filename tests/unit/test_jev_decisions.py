"""Jev intent routing and evidence reranking must fail closed.

The contract these tests defend is narrow and absolute: when Jev has no
opinion, the caller must get None and keep whatever it was doing. A routing
decision must never be invented from a missing key, a transport error, a
malformed body, an unoffered option, or a low-confidence answer, and retrieval
must never come back emptier than it went in.
"""
from __future__ import annotations

import httpx
import pytest

from packages.decisions.intent import INTENTS, MIN_CONFIDENCE, IntentDecision, classify_intent
from packages.decisions.jev_client import JevClient
from packages.decisions.rerank import (
    MAX_CANDIDATES,
    RELEVANCE_LEVELS,
    RerankResult,
    rerank_evidence,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("TYPESAFE_API_KEY", "JEV_MODEL", "JEV_ENDPOINT", "JEV_ENABLED"):
        monkeypatch.delenv(name, raising=False)


def _client(payload, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, request=request)

    return JevClient(api_key="k", transport=httpx.MockTransport(handler))


def _choice(choice_value, confidence=0.9):
    return {
        "model": "jev-1.13.0",
        "answers": {
            "intent": {
                "type": "choice",
                "choice": choice_value,
                "confidence": confidence,
                "probabilities": {choice_value: confidence},
            }
        },
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }


# --------------------------------------------------------------------------
# Intent routing
# --------------------------------------------------------------------------


def test_confident_choice_becomes_a_decision():
    decision = classify_intent("what did NVDA do today?", client=_client(_choice("market_data")))
    assert isinstance(decision, IntentDecision)
    assert decision.intent == "market_data"
    assert decision.model == "jev-1.13.0"


def test_no_key_means_no_opinion():
    assert classify_intent("anything", client=JevClient(api_key="")) is None


def test_transport_failure_is_not_a_default_intent():
    def boom(request):
        raise httpx.ConnectError("down")

    assert classify_intent("x", client=JevClient(api_key="k", transport=httpx.MockTransport(boom))) is None


def test_upstream_error_status_is_not_a_default_intent():
    assert classify_intent("x", client=_client({"detail": "nope"}, status=500)) is None


def test_an_option_we_never_offered_is_rejected():
    assert classify_intent("x", client=_client(_choice("delete_everything"))) is None


def test_low_confidence_is_treated_as_no_opinion():
    assert classify_intent("x", client=_client(_choice("chat", confidence=MIN_CONFIDENCE - 0.01))) is None
    assert classify_intent("x", client=_client(_choice("chat", confidence=MIN_CONFIDENCE + 0.01))) is not None


def test_malformed_answer_shape_is_rejected():
    bad = {"model": "jev-1.13.0", "answers": {"intent": {"type": "noul", "noul": 0.9}}, "usage": {}}
    assert classify_intent("x", client=_client(bad)) is None


def test_empty_input_is_never_sent():
    assert classify_intent("   ", client=_client(_choice("chat"))) is None


def test_every_offered_intent_is_routable_by_name():
    for name in INTENTS:
        decision = classify_intent("x", client=_client(_choice(name)))
        assert decision is not None and decision.intent == name


# --------------------------------------------------------------------------
# Evidence reranking
# --------------------------------------------------------------------------


def _scores(values: dict[str, float]):
    return {
        "model": "jev-1.13.0",
        "answers": {
            f"relevance_{k}": {"type": "score", "score": v, "confidence": 0.8}
            for k, v in values.items()
        },
        "usage": {"input_tokens": 50, "output_tokens": 5},
    }


def test_candidates_are_ordered_by_score():
    client = _client(_scores({"0": 0.4, "1": 3.9, "2": 2.5}))
    result = rerank_evidence("q", ["weak", "strong", "middling"], client=client)
    assert isinstance(result, RerankResult)
    assert [item.text for item in result.kept][0] == "strong"
    assert result.model == "jev-1.13.0"


def test_provenance_survives_reranking():
    client = _client(_scores({"0": 0.1, "1": 4.0}))
    result = rerank_evidence("q", ["first", "second"], client=client)
    assert result is not None
    # The kept item still points at where it came from in the input.
    assert result.kept[0].index == 1


def test_no_key_keeps_the_original_order():
    assert rerank_evidence("q", ["a", "b"], client=JevClient(api_key="")) is None


def test_transport_failure_never_empties_the_evidence():
    def boom(request):
        raise httpx.ConnectError("down")

    assert rerank_evidence("q", ["a", "b"], client=JevClient(api_key="k", transport=httpx.MockTransport(boom))) is None


def test_entirely_malformed_answers_are_not_read_as_irrelevant():
    client = _client({"model": "jev-1.13.0", "answers": {}, "usage": {}})
    assert rerank_evidence("q", ["a", "b"], client=client) is None


def test_all_below_threshold_still_returns_one_candidate():
    """Returning nothing would silently blank a research run, so the best
    candidate is kept even when it scores poorly."""
    client = _client(_scores({"0": 0.1, "1": 0.2}))
    result = rerank_evidence("q", ["a", "b"], client=client)
    assert result is not None and len(result.kept) == 1
    assert result.kept[0].score == pytest.approx(0.2)


def test_candidate_count_is_bounded():
    """Only the first window is sent; the rest keep their original position."""
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.read().decode())
        sent.extend(body["questions"].keys())
        return httpx.Response(
            200,
            json=_scores({str(i): 3.0 for i in range(MAX_CANDIDATES)}),
            request=request,
        )

    client = JevClient(api_key="k", transport=httpx.MockTransport(handler))
    many = [f"doc-{i}" for i in range(MAX_CANDIDATES + 10)]
    result = rerank_evidence("q", many, client=client)
    assert result is not None
    assert len(sent) == MAX_CANDIDATES          # questions sent, not candidates


def test_rubric_is_ordered_and_descriptive():
    # A score is a position on this scale; levels must stand on their own.
    assert len(RELEVANCE_LEVELS) >= 3
    assert all(isinstance(level, str) and level.strip() for level in RELEVANCE_LEVELS)


def test_empty_inputs_are_never_sent():
    client = _client(_scores({"0": 3.0}))
    assert rerank_evidence("", ["a"], client=client) is None
    assert rerank_evidence("q", [], client=client) is None
    assert rerank_evidence("q", ["   "], client=client) is None
