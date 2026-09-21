"""The Jev client must fail closed and stay cheap to test.

Every test here runs without a network and without an API key, which is the
point: the client is exercised through ``httpx.MockTransport`` so the failure
paths -- the ones that matter -- are as easy to reach as the happy path.
"""
from __future__ import annotations

import json

import httpx
import pytest

from packages.decisions.jev_client import (
    JevClient,
    JevError,
    JevUnavailable,
    choice,
    noul,
    score,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """A developer's own JEV_* environment must not steer these tests."""
    for name in ("TYPESAFE_API_KEY", "JEV_MODEL", "JEV_ENDPOINT",
                 "JEV_TIMEOUT_SECONDS", "JEV_ENABLED"):
        monkeypatch.delenv(name, raising=False)


def _client(handler, **kwargs):
    return JevClient(api_key="test-key", transport=httpx.MockTransport(handler), **kwargs)


_OK_BODY = {
    "model": "jev-1.13.0",
    "answers": {
        "bundle_trustworthy": {"type": "noul", "noul": 0.93},
        "regime": {"type": "choice", "choice": "risk_on",
                   "probabilities": {"risk_on": 0.7, "risk_off": 0.3},
                   "confidence": 0.81},
        "stress": {"type": "score", "score": 1.2, "confidence": 0.66},
    },
    "usage": {"input_tokens": 812, "output_tokens": 41},
}


# --------------------------------------------------------------------------
# Fail closed -- the most important behaviour here
# --------------------------------------------------------------------------

def test_no_key_means_not_configured_and_refuses_to_call():
    client = JevClient(api_key="")
    assert client.configured is False
    with pytest.raises(JevUnavailable):
        client.ask({"a": 1}, {"q": noul("is it fine?")})


def test_kill_switch_disables_even_with_a_key():
    client = JevClient(api_key="test-key", enabled=False)
    assert client.configured is False
    with pytest.raises(JevUnavailable):
        client.ask({"a": 1}, {"q": noul("is it fine?")})


def test_key_is_never_exposed_on_the_status_dict():
    client = JevClient(api_key="super-secret-key")
    status = client.status
    assert status["configured"] is True
    assert "super-secret-key" not in str(status)


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------

def test_successful_call_returns_answers_and_versioned_model():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode()
        return httpx.Response(200, json=_OK_BODY)

    result = _client(handler).ask(
        {"available": True},
        {"bundle_trustworthy": noul("is the data fresh?"),
         "regime": choice("what regime?", {"risk_on": None, "risk_off": None})},
    )
    assert result["answers"]["bundle_trustworthy"]["noul"] == 0.93
    # The versioned id, not the alias -- so a stored judgment stays auditable.
    assert result["model"] == "jev-1.13.0"
    assert result["usage"]["input_tokens"] == 812
    assert seen["auth"] == "Bearer test-key"
    assert "api.typesafe.ai/v1/systemone" in seen["url"]
    sent = json.loads(seen["body"])
    assert sent["model"] == "jev-latest"
    assert sent["state"] == {"available": True}
    assert sent["questions"]["regime"]["type"] == "choice"


def test_retries_once_on_rate_limit_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"detail": "slow down"},
                                  headers={"retry-after": "0"})
        return httpx.Response(200, json=_OK_BODY)

    result = _client(handler).ask({"a": 1}, {"q": noul("ok?")})
    assert calls["n"] == 2
    assert result["answers"]


def test_retries_once_on_transport_failure():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectTimeout("timed out")
        return httpx.Response(200, json=_OK_BODY)

    result = _client(handler).ask({"a": 1}, {"q": noul("ok?")})
    assert calls["n"] == 2
    assert result["answers"]


# --------------------------------------------------------------------------
# Error surfaces
# --------------------------------------------------------------------------

def test_auth_failure_is_not_retried_and_carries_the_status():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"detail": "bad key"})

    with pytest.raises(JevError) as excinfo:
        _client(handler).ask({"a": 1}, {"q": noul("ok?")})
    assert excinfo.value.status == 401
    assert calls["n"] == 1          # a bad key will not fix itself


def test_persistent_rate_limit_surfaces_after_the_retry_budget():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "slow down"})

    with pytest.raises(JevError) as excinfo:
        _client(handler).ask({"a": 1}, {"q": noul("ok?")})
    assert excinfo.value.status == 429


def test_non_json_body_is_an_error_not_a_silent_empty_answer():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway</html>")

    with pytest.raises(JevError, match="non-JSON"):
        _client(handler).ask({"a": 1}, {"q": noul("ok?")})


def test_json_without_answers_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "jev-1.13.0"})

    with pytest.raises(JevError, match="no answers"):
        _client(handler).ask({"a": 1}, {"q": noul("ok?")})


def test_empty_question_map_is_rejected_before_any_call():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not reach the network")

    with pytest.raises(ValueError, match="at least one question"):
        _client(handler).ask({"a": 1}, {})


# --------------------------------------------------------------------------
# Question builders
# --------------------------------------------------------------------------

def test_noul_includes_criteria_only_when_given():
    assert noul("is it true?") == {"type": "noul", "instructions": "is it true?"}
    with_criteria = noul("is it true?", true_means="yes", false_means="no")
    assert with_criteria["criteria"] == {"true": "yes", "false": "no"}


def test_choice_requires_options():
    assert choice("pick", {"a": None})["criteria"] == {"a": None}
    with pytest.raises(ValueError):
        choice("pick", {})


def test_score_requires_two_levels():
    assert score("how bad?", ["calm", "bad", "severe"])["criteria"][2] == "severe"
    with pytest.raises(ValueError):
        score("how bad?", ["only one"])
