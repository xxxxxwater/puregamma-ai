"""The Agent's built-in plugin inventory must describe the real tool surface.

A capability list that drifts from the code is worse than no list: it tells a
user (and an operator) that the Agent can do something it cannot. This test
reads the tool registry's own source and refuses any declared tool that is not a
key of `self.tools`, without needing a database.
"""
from __future__ import annotations

import ast
from pathlib import Path

from apps.api.services.agent_plugins import PLUGIN_SPECS, SOURCE_LABELS, _entitlement_gate

TOOLS_MODULE = Path(__file__).resolve().parents[2] / "packages" / "agents" / "chat" / "tools.py"


def registry_tool_names() -> set[str]:
    """The string keys of the `self.tools = {...}` literal, read from source."""
    tree = ast.parse(TOOLS_MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        # `self.tools: dict[...] = {...}` is an AnnAssign, `self.tools = {...}` is
        # an Assign; both forms carry the same table.
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign):
            target, value = (node.targets[0] if node.targets else None), node.value
        else:
            continue
        if not isinstance(target, ast.Attribute) or target.attr != "tools":
            continue
        if not isinstance(value, ast.Dict):
            continue
        keys = {k.value for k in value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if keys:
            return keys
    raise AssertionError("AgentToolRegistry's tool table was not found; the parser needs updating")


def test_every_declared_tool_exists_in_the_registry():
    implemented = registry_tool_names()
    declared = {tool for spec in PLUGIN_SPECS for tool in spec.tools}
    assert declared, "the inventory declares no tools at all"
    assert declared <= implemented, f"inventory names unregistered tools: {sorted(declared - implemented)}"


def test_plugin_ids_are_unique_and_named():
    ids = [spec.id for spec in PLUGIN_SPECS]
    assert len(ids) == len(set(ids))
    assert all(spec.id and spec.name_zh and spec.name_en for spec in PLUGIN_SPECS)
    assert all(spec.description_zh and spec.description_en for spec in PLUGIN_SPECS)
    assert all(spec.service for spec in PLUGIN_SPECS), "every plugin names the module that implements it"


def test_a_tool_less_plugin_is_infrastructure_not_an_accident():
    for spec in PLUGIN_SPECS:
        if not spec.tools:
            assert spec.infrastructure, f"{spec.id} provides no tools and is not marked infrastructure"


def test_requires_names_a_known_data_source():
    for spec in PLUGIN_SPECS:
        for source in spec.requires:
            assert source in SOURCE_LABELS, f"{spec.id} requires an unknown source {source!r}"


def test_the_gate_matches_how_the_tools_behave():
    all_plans = {"allowed_data_sources": ["all"]}
    assert _entitlement_gate(all_plans, ("market",)) == (True, None)
    # No requirement at all: available to every plan.
    assert _entitlement_gate({"allowed_data_sources": []}, ()) == (True, None)
    # A gated source the plan lacks disables the plugin with a reason, never
    # silently: the UI shows why.
    enabled, reason = _entitlement_gate({"allowed_data_sources": ["rss"]}, ("portfolio",))
    assert enabled is False and reason == "plan_required"
    assert _entitlement_gate({"allowed_data_sources": ["rss"]}, ("rss",)) == (True, None)
