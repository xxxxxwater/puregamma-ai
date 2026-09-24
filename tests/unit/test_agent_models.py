"""The Agent model catalog is data, and the selector must match what runs.

Two failure modes are pinned here, both of which reach a paying user:
an entry the selector offers but the server refuses (AGENT_MODEL_INVALID after
the user picked it), and a malformed entry that renders a raw provider id.
"""
from __future__ import annotations

from apps.api.config import DEFAULT_OPENAI_AGENT_MODELS, _csv, _model_label


def parse(value: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        parsed for parsed in (_model_label(item) for item in _csv(value)) if parsed is not None
    )


def test_the_shipped_default_is_the_current_gpt_line():
    models = parse(DEFAULT_OPENAI_AGENT_MODELS)
    assert [identifier for identifier, _ in models] == ["gpt-6-luna", "gpt-6-sol", "gpt-6-astra"]
    assert all(label and not label.startswith("gpt-") for _, label in models), "labels are human names"


def test_every_entry_must_carry_both_an_id_and_a_label():
    assert _model_label("gpt-6-luna:Luna") == ("gpt-6-luna", "Luna")
    assert _model_label("gpt-6-luna") is None          # no label: would render a raw id
    assert _model_label(":Luna") is None               # no id: would offer an unrunnable model
    assert _model_label("   ") is None
    assert _model_label("gpt-6-luna:") is None


def test_a_malformed_entry_is_dropped_without_losing_the_valid_ones():
    models = parse("gpt-6-luna:Luna,broken,gpt-6-sol:Sol")
    assert [identifier for identifier, _ in models] == ["gpt-6-luna", "gpt-6-sol"]
