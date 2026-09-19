"""Jev in the gateway catalog: pricing, capability honesty, and the real call.

Jev is the first catalogued model that is not a chat model, so these tests pin
the two things that makes easy to get wrong:

* its price is **input-only** -- $42 per Btok is $0.042 per Mtok, and output
  tokens are free. A zero-rate entry for `output` would also produce 0, but the
  catalog simply does not carry one, so the test asserts the billing path
  charges nothing without a special case.
* every chat-shaped capability must be **refused**, not approximated. A caller
  who sends `chat/completions` must get a capability error, never a
  conversation-shaped reply built out of a judgment.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest

from packages.gateway.catalog import provider_models
from packages.gateway.contracts import (
    GatewayCapabilityUnavailable,
    GatewayProviderError,
    GatewayUsage,
)
from packages.gateway.pricing import final_prices, normalize_official_prices, usage_cost
from packages.gateway.registry import provider_registry

# --------------------------------------------------------------------------
# Catalog: the price is USD-native and input-only
# --------------------------------------------------------------------------


def _jev():
    models = {item.public_id: item for item in provider_models("typesafe")}
    assert "jev" in models, "jev must be catalogued"
    return models["jev"]


def test_jev_is_catalogued_against_the_versioned_alias():
    jev = _jev()
    # The public id stays stable while the upstream id is the moving alias.
    assert jev.provider_model_id == "jev-latest"
    assert jev.source_reference == "https://docs.typesafe.ai/models"


def test_price_is_usd_native_and_input_only():
    """$42 per Btok == $0.042 per Mtok. Output has no tariff at all."""
    prices = normalize_official_prices(_jev().official_prices)
    assert prices["input"]["usd"] == "0.042"
    assert prices["input"]["unit"] == "per_million_tokens"
    # Absent, not zero: output is free by omission.
    assert "output" not in prices
    assert "cache" not in prices


def test_metadata_records_why_no_fx_policy_is_needed():
    """The CNY providers gate on an approved conversion; this one must not."""
    metadata = _jev().metadata
    assert metadata["official_currency"] == "USD"
    assert metadata["output_priced_as"] == "free"
    assert metadata["official_price_per_btok"] == "42"
    # A caller needs to know the usable ceiling, which is the smaller budget.
    assert metadata["state_budget_tokens"] == 32768


def test_capabilities_say_no_to_chat_rather_than_omitting_it():
    capabilities = _jev().capabilities
    for name in ("chat", "stream", "tool_calling", "json_mode"):
        assert capabilities[name] is False, f"{name} must be explicitly false"
    assert capabilities["system_one"] is True
    assert capabilities["max_context_tokens"] == 65536


# --------------------------------------------------------------------------
# Billing
# --------------------------------------------------------------------------


def test_one_million_input_tokens_costs_one_input_rate():
    cost = usage_cost(_jev().official_prices, GatewayUsage(input_tokens=1_000_000))
    assert cost == Decimal("0.042")


def test_output_tokens_are_free_but_still_counted_as_traffic():
    """The ledger must see the output; the tariff must not charge for it."""
    priced = _jev().official_prices
    input_only = usage_cost(priced, GatewayUsage(input_tokens=1_000_000))
    with_output = usage_cost(
        priced, GatewayUsage(input_tokens=1_000_000, output_tokens=5_000_000)
    )
    assert with_output == input_only == Decimal("0.042")


def test_cost_scales_linearly_with_state_size():
    # A 500k-token state is half a Mtok, so half the rate.
    cost = usage_cost(_jev().official_prices, GatewayUsage(input_tokens=500_000))
    assert cost == Decimal("0.021")


def test_markup_applies_to_the_input_rate():
    final = final_prices(_jev().official_prices, markup_bps=2_000)  # +20%
    # The engine quantizes to 8 decimals, so compare numerically.
    assert Decimal(final["input"]["usd"]) == Decimal("0.0504")
    assert "output" not in final


def test_a_jev_request_is_priced_far_below_a_chat_turn():
    """Sanity: a typical 2k-token state is a rounding error, not a line item."""
    cost = usage_cost(_jev().official_prices, GatewayUsage(input_tokens=2_000, output_tokens=48))
    assert cost == Decimal("0.00008400")


# --------------------------------------------------------------------------
# The provider contract
# --------------------------------------------------------------------------


def _settings(**overrides):
    from apps.api.config import get_settings

    settings = get_settings()
    for key, value in overrides.items():
        object.__setattr__(settings, key, value)
    return settings


def _provider(api_key="test-key", **metadata):
    from packages.gateway.providers.typesafe import TypeSafeGatewayProvider

    settings = _settings(gateway_typesafe_api_key=api_key)
    return TypeSafeGatewayProvider(settings, {"base_url": "https://api.typesafe.ai/v1", **metadata})


def test_provider_is_registered_under_typesafe():
    assert "typesafe" in provider_registry.names()
    adapter = provider_registry.create("typesafe", _settings(gateway_typesafe_api_key="k"), {})
    assert adapter.provider_name == "typesafe"


@pytest.mark.parametrize("capability", ["chat", "stream", "embedding", "image", "audio", "rerank"])
def test_chat_shaped_capabilities_are_refused_not_faked(capability):
    adapter = _provider()
    with pytest.raises(GatewayCapabilityUnavailable) as excinfo:
        getattr(adapter, capability)("jev-latest", {})
    assert excinfo.value.code == "GATEWAY_CAPABILITY_UNAVAILABLE"
    # 400 + not retryable: retrying a capability that does not exist is waste.
    assert excinfo.value.status_code == 400
    assert excinfo.value.retryable is False


def test_unconfigured_provider_refuses_before_any_network_call():
    adapter = _provider(api_key="")
    with pytest.raises(GatewayProviderError) as excinfo:
        adapter.systemOne("jev-latest", {"state": "x", "questions": {"q": {}}})
    assert excinfo.value.code == "GATEWAY_PROVIDER_UNCONFIGURED"


def test_system_one_requires_a_non_empty_questions_map():
    adapter = _provider()
    for bad in ({}, {"state": "x"}, {"state": "x", "questions": {}}):
        with pytest.raises(GatewayProviderError) as excinfo:
            adapter.systemOne("jev-latest", bad)
        assert excinfo.value.code == "GATEWAY_INVALID_REQUEST"


# --------------------------------------------------------------------------
# The upstream call, driven through a fake transport
# --------------------------------------------------------------------------

_ANSWER = {
    "model": "jev-1.13.0",
    "answers": {"trustworthy": {"type": "noul", "noul": 0.93}},
    "usage": {"input_tokens": 812, "output_tokens": 41},
}


class _FakeClient:
    """Captures the outgoing request and replays a canned response."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None):
        self.calls.append(("POST", url, headers, json))
        return httpx.Response(200, json=_ANSWER, request=httpx.Request("POST", url))

    def get(self, url, headers=None):
        self.calls.append(("GET", url, headers, None))
        return httpx.Response(200, json={"data": []}, request=httpx.Request("GET", url))


@pytest.fixture
def fake_http(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client)
    return client


def test_system_one_posts_the_documented_shape(fake_http):
    adapter = _provider()
    body = adapter.systemOne(
        "jev-latest",
        {"state": {"available": True}, "questions": {"trustworthy": {"type": "noul"}},
         # Routing/accounting fields must not cross the provider boundary.
         "api_key_id": "internal", "request_id": "internal"},
    )
    assert body["model"] == "jev-1.13.0"

    method, url, headers, payload = fake_http.calls[-1]
    assert method == "POST"
    assert url == "https://api.typesafe.ai/v1/systemone"
    assert headers["Authorization"] == "Bearer test-key"
    assert payload["model"] == "jev-latest"
    assert payload["state"] == {"available": True}
    assert payload["questions"] == {"trustworthy": {"type": "noul"}}
    assert "api_key_id" not in payload and "request_id" not in payload


def test_system_one_returns_the_versioned_model_not_the_alias(fake_http):
    """An alias moves; a stored answer has to carry the version that made it."""
    adapter = _provider()
    body = adapter.systemOne("jev-latest", {"state": "x", "questions": {"q": {}}})
    assert body["model"] == "jev-1.13.0"


def test_http_error_is_surfaced_and_classified():
    class _ErrorClient(_FakeClient):
        def post(self, url, headers=None, json=None):
            return httpx.Response(401, json={"detail": "bad key"},
                                  request=httpx.Request("POST", url))

    adapter = _provider()
    import httpx as _httpx

    original = _httpx.Client
    _httpx.Client = lambda **kwargs: _ErrorClient()
    try:
        with pytest.raises(GatewayProviderError) as excinfo:
            adapter.systemOne("jev-latest", {"state": "x", "questions": {"q": {}}})
    finally:
        _httpx.Client = original
    assert excinfo.value.status_code == 400      # a bad key will not fix itself
    assert excinfo.value.retryable is False


def test_response_without_answers_is_rejected():
    class _BadClient(_FakeClient):
        def post(self, url, headers=None, json=None):
            return httpx.Response(200, json={"model": "jev-1.13.0"},
                                  request=httpx.Request("POST", url))

    adapter = _provider()
    import httpx as _httpx

    original = _httpx.Client
    _httpx.Client = lambda **kwargs: _BadClient()
    try:
        with pytest.raises(GatewayProviderError) as excinfo:
            adapter.systemOne("jev-latest", {"state": "x", "questions": {"q": {}}})
    finally:
        _httpx.Client = original
    assert excinfo.value.code == "GATEWAY_PROVIDER_INVALID_RESPONSE"


# --------------------------------------------------------------------------
# Metering bridge
# --------------------------------------------------------------------------


def test_token_usage_maps_the_system_one_envelope():
    adapter = _provider()
    usage = adapter.tokenUsage(_ANSWER)
    assert usage.input_tokens == 812
    assert usage.output_tokens == 41
    # Jev has no cache, reasoning or unit-priced skus.
    assert usage.cache_tokens == 0
    assert usage.reasoning_tokens == 0


def test_token_usage_survives_a_missing_or_malformed_usage_block():
    adapter = _provider()
    for payload in ({}, {"usage": None}, {"usage": {"input_tokens": "oops"}}):
        usage = adapter.tokenUsage(payload)
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0


def test_metered_usage_costs_input_only_end_to_end():
    """The whole point, end to end: upstream usage -> catalog price -> cost."""
    adapter = _provider()
    cost = usage_cost(_jev().official_prices, adapter.tokenUsage(_ANSWER))
    assert cost == (Decimal(812) * Decimal("0.042") / Decimal(1_000_000)).quantize(
        Decimal("0.00000001")
    )


def test_health_check_uses_the_models_path(fake_http):
    adapter = _provider()
    assert adapter.healthCheck()["status"] == "ok"
    method, url, _, _ = fake_http.calls[-1]
    assert (method, url) == ("GET", "https://api.typesafe.ai/v1/models")


def test_pricing_exposes_only_entries_that_carry_a_reviewed_price():
    adapter = _provider()
    priced = adapter.getPricing()
    assert [item.public_id for item in priced] == ["jev"]
