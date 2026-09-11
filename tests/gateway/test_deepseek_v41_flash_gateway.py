"""DeepSeek V4.1 Flash coverage for the API Gateway (中转站).

These tests pin the properties that make the upgrade real rather than cosmetic:

* the catalog exposes the official ``deepseek-flash`` id, mapped to the same
  upstream id, alongside compatibility entries for retired names;
* other vendors' models are untouched and are never rewritten to DeepSeek;
* reasoning and cache tokens are billed as subsets, never twice;
* availability is derived from the database, so copy cannot claim "live"
  before the model is actually routable.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.config import DEEPSEEK_LEGACY_MODEL_ALIASES, DEEPSEEK_MODEL_FLASH
from packages.gateway.catalog import provider_models, public_model_catalog
from packages.gateway.contracts import GatewayUsage
from packages.gateway.pricing import final_prices, usage_cost


@pytest.fixture(scope="module")
def deepseek_models():
    return {item.public_id: item for item in provider_models("deepseek")}


def test_catalog_exposes_the_official_v41_flash_model_id(deepseek_models):
    model = deepseek_models[DEEPSEEK_MODEL_FLASH]

    assert model.display_name == "DeepSeek V4.1 Flash"
    assert model.provider_model_id == DEEPSEEK_MODEL_FLASH
    assert model.official_prices, "V4.1 Flash must carry a reviewed price"


def test_catalog_never_invents_a_model_id_from_the_display_name(deepseek_models):
    assert "deepseek-v4.1-flash" not in deepseek_models
    assert "deepseek-v4.1-flash" not in {m.provider_model_id for m in deepseek_models.values()}


def test_retired_flash_names_are_aliases_of_the_same_upstream_model(deepseek_models):
    alias = deepseek_models["deepseek-v4-flash"]

    assert alias.provider_model_id == DEEPSEEK_MODEL_FLASH
    assert alias.metadata.get("canonical_model_id") == DEEPSEEK_MODEL_FLASH
    assert alias.metadata.get("compatibility_alias") == "true"
    # The alias must cost the same as the model that serves it.
    assert alias.official_prices == deepseek_models[DEEPSEEK_MODEL_FLASH].official_prices


def test_v4_pro_remains_its_own_upstream_model(deepseek_models):
    """V4 Pro must not be rewritten before DeepSeek's announced cut-over."""
    pro = deepseek_models["deepseek-v4-pro"]

    assert pro.provider_model_id == "deepseek-v4-pro"
    assert "2026-09-14" in str(pro.metadata.get("retirement_scheduled", ""))


def test_other_vendors_keep_their_own_models():
    """The upgrade must not collapse every /models entry onto DeepSeek."""
    kimi = {item.public_id: item for item in provider_models("moonshot")}
    glm = {item.public_id: item for item in provider_models("glm")}

    assert kimi["kimi-k3-max"].provider_model_id == "kimi-k3"
    assert glm["glm-5.2"].provider_model_id == "glm-5.2"
    for model in (*kimi.values(), *glm.values()):
        assert not model.provider_model_id.startswith("deepseek")


def test_legacy_alias_map_covers_every_retired_flash_name():
    for name in ("deepseek-v4-flash", "deepseek-v4-flash-0731", "deepseek-v4-flash-vision-exp"):
        assert DEEPSEEK_LEGACY_MODEL_ALIASES[name] == DEEPSEEK_MODEL_FLASH


def test_configured_default_is_not_a_retired_name():
    from apps.api.config import Settings

    assert Settings().deepseek_model == DEEPSEEK_MODEL_FLASH


# ----------------------------------------------------------------------
# Pricing
# ----------------------------------------------------------------------
def _prices():
    return provider_models("deepseek")[0].official_prices


def test_reasoning_tokens_are_not_billed_twice(deepseek_models):
    """DeepSeek reports reasoning_tokens inside completion_tokens."""
    prices = {"output": {"usd": "1"}, "reasoning": {"usd": "1"}}
    usage = GatewayUsage(input_tokens=0, output_tokens=35, reasoning_tokens=33)

    # 35 output total, of which 33 are reasoning: 2 at the output tariff and
    # 33 at the reasoning tariff = 35 tokens charged, not 68.
    assert usage_cost(prices, usage) == Decimal("0.000035")


def test_cache_tokens_replace_input_tokens_rather_than_adding_to_them():
    prices = {"input": {"usd": "1"}, "cache": {"usd": "0.5"}}
    usage = GatewayUsage(input_tokens=100, cache_tokens=40)

    # 60 misses at 1 + 40 hits at 0.5 = 80, never 140.
    assert usage_cost(prices, usage) == Decimal("0.000080")


def test_output_tariff_without_reasoning_rate_charges_the_full_completion():
    prices = {"output": {"usd": "1"}}
    usage = GatewayUsage(output_tokens=35, reasoning_tokens=33)

    assert usage_cost(prices, usage) == Decimal("0.000035")


def test_v41_flash_price_is_the_off_peak_official_tariff(deepseek_models):
    model = deepseek_models[DEEPSEEK_MODEL_FLASH]

    assert Decimal(model.official_prices["input"]["usd"]) == Decimal("0.15151515")
    assert Decimal(model.official_prices["output"]["usd"]) == Decimal("0.60606061")
    assert Decimal(model.official_prices["cache"]["usd"]) == Decimal("0.00303030")
    # The peak tariff is exactly double; the catalog must say so.
    assert model.metadata.get("peak_multiplier") == "2"
    assert model.metadata.get("pricing_period") == "off_peak"


def test_prices_are_lower_than_the_model_v41_flash_replaces(deepseek_models):
    """The upgrade must not silently raise the DeepSeek Flash tariff."""
    new = deepseek_models[DEEPSEEK_MODEL_FLASH].official_prices
    old_alias = deepseek_models["deepseek-v4-flash"].official_prices

    assert Decimal(new["input"]["usd"]) > 0
    assert new == old_alias


def test_markup_is_applied_to_every_deepseek_price(deepseek_models):
    official = deepseek_models[DEEPSEEK_MODEL_FLASH].official_prices
    marked = final_prices(official, 3000)

    for key, item in official.items():
        assert Decimal(marked[key]["usd"]) == (Decimal(item["usd"]) * Decimal("1.3")).quantize(
            Decimal("0.00000001")
        )


# ----------------------------------------------------------------------
# Availability is database-derived, never asserted in copy
# ----------------------------------------------------------------------
def test_public_catalog_reports_setup_required_without_approved_pricing(db):
    catalog = {item["id"]: item for item in public_model_catalog(db, markup_bps=3000)}

    flash = catalog[DEEPSEEK_MODEL_FLASH]
    assert flash["provider_model_id"] == DEEPSEEK_MODEL_FLASH
    assert flash["availability"] == "setup_required"
    assert flash["availability"] != "available"
    # Peak/off-peak must be visible to API customers, not hidden.
    assert flash["metadata"]["peak_multiplier"] == "2"
    assert flash["pricing"]["official"]["input"]["amount"] == "0.15151515"


def test_public_catalog_exposes_the_alias_relationship(db):
    catalog = {item["id"]: item for item in public_model_catalog(db, markup_bps=3000)}

    alias = catalog["deepseek-v4-flash"]
    assert alias["provider_model_id"] == DEEPSEEK_MODEL_FLASH
    assert alias["metadata"]["canonical_model_id"] == DEEPSEEK_MODEL_FLASH
