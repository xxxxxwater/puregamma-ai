"""DeepSeek V4.1 Flash request-contract tests.

These pin what actually leaves the process for the upstream API, which is the
only thing that decides whether the upgrade is real: the model id, the thinking
switch, and the parameters that are silently ignored while thinking is on.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from apps.api.config import DEEPSEEK_MODEL_FLASH, Settings
from packages.agents.llm.deepseek_provider import DeepSeekProvider
from packages.agents.llm.schemas import ChatMessage


class _Recorder:
    """Capture the exact kwargs handed to the OpenAI SDK."""

    def __init__(self, *, content="OK", reasoning_tokens=0, stream_chunks=("O", "K")):
        self.calls: list[dict] = []
        self._content = content
        self._reasoning_tokens = reasoning_tokens
        self._stream_chunks = stream_chunks

    def completions_create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            chunks = []
            for piece in self._stream_chunks:
                chunks.append(
                    SimpleNamespace(
                        usage=None,
                        choices=[SimpleNamespace(delta=SimpleNamespace(content=piece))],
                    )
                )
            chunks.append(
                SimpleNamespace(
                    usage=SimpleNamespace(
                        prompt_tokens=11,
                        completion_tokens=2,
                        completion_tokens_details=SimpleNamespace(reasoning_tokens=self._reasoning_tokens),
                    ),
                    choices=[],
                )
            )
            return iter(chunks)
        details = SimpleNamespace(reasoning_tokens=self._reasoning_tokens)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(
                prompt_tokens=11,
                completion_tokens=1 + self._reasoning_tokens,
                completion_tokens_details=details,
            ),
        )


def _install_fake_openai(monkeypatch, recorder: _Recorder) -> None:
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=recorder.completions_create)))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **kwargs: client))


def _settings(**overrides) -> Settings:
    values = {
        "deepseek_api_key": "test-only-key",
        "deepseek_model": DEEPSEEK_MODEL_FLASH,
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_thinking_mode": "disabled",
        "agent_temperature": 0.2,
        "agent_max_output_tokens": 1200,
        "agent_request_timeout_ms": 60000,
    }
    values.update(overrides)
    return Settings(**values)


def test_provider_sends_the_official_model_id(monkeypatch):
    recorder = _Recorder()
    _install_fake_openai(monkeypatch, recorder)
    provider = DeepSeekProvider(_settings())

    provider.chat([ChatMessage(role="user", content="hi")], task_type="agent_chat")

    assert recorder.calls[0]["model"] == "deepseek-flash"


def test_retired_configured_name_still_sends_the_official_model_id(monkeypatch):
    """A deployment that has not rolled DEEPSEEK_MODEL must not send a dead id."""
    recorder = _Recorder()
    _install_fake_openai(monkeypatch, recorder)
    provider = DeepSeekProvider(_settings(deepseek_model="deepseek-v4-flash"))

    response = provider.chat([ChatMessage(role="user", content="hi")], task_type="agent_chat")

    assert recorder.calls[0]["model"] == "deepseek-flash"
    # The reported model is the one that really served the request.
    assert response.model == "deepseek-flash"


def test_user_named_other_model_is_not_rewritten(monkeypatch):
    recorder = _Recorder()
    _install_fake_openai(monkeypatch, recorder)
    provider = DeepSeekProvider(_settings(deepseek_model="deepseek-v4-pro"))

    provider.chat([ChatMessage(role="user", content="hi")], task_type="agent_chat")

    assert recorder.calls[0]["model"] == "deepseek-v4-pro"


# ----------------------------------------------------------------------
# Thinking mode
# ----------------------------------------------------------------------
def test_thinking_is_disabled_explicitly_on_platform_paths(monkeypatch):
    recorder = _Recorder()
    _install_fake_openai(monkeypatch, recorder)

    DeepSeekProvider(_settings()).chat([ChatMessage(role="user", content="hi")], task_type="agent_chat")

    call = recorder.calls[0]
    assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    # Temperature is only meaningful with thinking off.
    assert call["temperature"] == 0.2
    assert "reasoning_effort" not in call


def test_thinking_enabled_sends_effort_and_omits_temperature(monkeypatch):
    recorder = _Recorder()
    _install_fake_openai(monkeypatch, recorder)

    DeepSeekProvider(
        _settings(deepseek_thinking_mode="enabled", deepseek_reasoning_effort="max")
    ).chat([ChatMessage(role="user", content="hi")], task_type="agent_chat")

    call = recorder.calls[0]
    assert call["extra_body"] == {"thinking": {"type": "enabled"}}
    assert call["reasoning_effort"] == "max"
    # DeepSeek ignores temperature while thinking; sending it would imply a
    # control the caller does not have.
    assert "temperature" not in call


def test_reasoning_tokens_are_reported_separately_from_completion(monkeypatch):
    recorder = _Recorder(reasoning_tokens=33)
    _install_fake_openai(monkeypatch, recorder)

    response = DeepSeekProvider(_settings(deepseek_thinking_mode="enabled")).chat(
        [ChatMessage(role="user", content="hi")], task_type="agent_chat"
    )

    assert response.reasoning_tokens == 33
    # DeepSeek includes reasoning inside completion_tokens; the provider must
    # not double count them into the total.
    assert response.completion_tokens == 34
    assert response.total_tokens == 45


# ----------------------------------------------------------------------
# Streaming
# ----------------------------------------------------------------------
def test_stream_disables_thinking_and_caps_output(monkeypatch):
    recorder = _Recorder()
    _install_fake_openai(monkeypatch, recorder)
    provider = DeepSeekProvider(_settings())

    chunks = list(provider.stream_chat([ChatMessage(role="user", content="hi")], task_type="agent_chat"))

    call = recorder.calls[0]
    assert call["stream"] is True
    assert call["model"] == "deepseek-flash"
    assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert call["max_tokens"] == 1200
    assert "".join(chunk.delta for chunk in chunks) == "OK"
    assert chunks[-1].done is True
    assert chunks[-1].model == "deepseek-flash"


def test_stream_with_thinking_does_not_cap_the_reasoning_budget(monkeypatch):
    """A max_tokens cap can be consumed entirely by reasoning, returning nothing."""
    recorder = _Recorder()
    _install_fake_openai(monkeypatch, recorder)

    list(
        DeepSeekProvider(_settings(deepseek_thinking_mode="enabled")).stream_chat(
            [ChatMessage(role="user", content="hi")], task_type="agent_chat"
        )
    )

    call = recorder.calls[0]
    assert "max_tokens" not in call
    assert call["extra_body"] == {"thinking": {"type": "enabled"}}


# ----------------------------------------------------------------------
# Structured output must stay validated, never silently fake success
# ----------------------------------------------------------------------
def test_json_mode_is_forwarded(monkeypatch):
    recorder = _Recorder(content='{"ok": true}')
    _install_fake_openai(monkeypatch, recorder)

    DeepSeekProvider(_settings()).chat(
        [ChatMessage(role="user", content="give json")],
        task_type="classification",
        response_format="json_object",
    )

    assert recorder.calls[0]["response_format"] == {"type": "json_object"}


def test_upstream_failure_raises_instead_of_returning_placeholder_content(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("upstream 429")

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=boom)))),
    )
    monkeypatch.setattr("time.sleep", lambda *_: None)
    provider = DeepSeekProvider(_settings())

    with pytest.raises(RuntimeError, match="429"):
        provider.chat([ChatMessage(role="user", content="hi")], task_type="agent_chat")

    assert provider.last_error is not None


def test_missing_key_provider_is_not_configured():
    provider = DeepSeekProvider(_settings(deepseek_api_key=""))

    assert provider.configured is False
    assert "DEEPSEEK_API_KEY" in provider.last_error
