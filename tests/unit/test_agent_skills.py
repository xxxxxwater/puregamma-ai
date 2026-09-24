"""The Agent skill mechanism, pinned to the DeepSeek Harness contract.

Upstream reference: ``dsh-v0.1.7-rc.1``,
``packages/skill/skill-filesystem`` (discovery + frontmatter) and
``packages/skill/tool-skill`` (catalog + ``/name`` invocation).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.services import agent_skills

SKILL = """---
name: market-research
description: Evidence-based market research.
whenToUse: >-
  Use when the user asks for market structure analysis.
metadata:
  legacy_slug: market_research
---

Build the evidence pack first.
"""


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_discovers_directory_bundles_and_flat_files(tmp_path: Path):
    write(tmp_path, "bundle-skill/SKILL.md", SKILL.replace("market-research", "bundle-skill"))
    write(tmp_path, "flat-skill.md", SKILL.replace("market-research", "flat-skill"))
    # Depth 3 is deliberately not discovered, exactly like upstream.
    write(tmp_path, "nested/deeper/SKILL.md", SKILL.replace("market-research", "too-deep"))
    assert [entry.name for entry in agent_skills.discover(tmp_path)] == ["bundle-skill", "flat-skill"]


def test_catalog_is_sorted_by_name_not_by_discovery_order(tmp_path: Path):
    write(tmp_path, "zulu/SKILL.md", SKILL.replace("market-research", "zulu"))
    write(tmp_path, "alpha/SKILL.md", SKILL.replace("market-research", "alpha"))
    assert [entry.name for entry in agent_skills.discover(tmp_path)] == ["alpha", "zulu"]


@pytest.mark.parametrize(
    "frontmatter",
    [
        "name: Not_Kebab\ndescription: x",          # name must be kebab-case
        "name: ok",                                   # missing description
        "name: ok\ndescription: ''",                  # empty description
        "name: ok\ndescription: x\nuserInvocable: false",  # camel-case alias is a hard error
        "name: ok\ndescription: x\nuser-invocable: maybe",  # not a boolean
    ],
)
def test_a_malformed_skill_is_dropped_not_permitted(tmp_path: Path, frontmatter: str):
    write(tmp_path, "broken/SKILL.md", f"---\n{frontmatter}\n---\n\nbody\n")
    assert agent_skills.discover(tmp_path) == ()


def test_boolean_spellings_upstream_accepts(tmp_path: Path):
    write(
        tmp_path,
        "user-only/SKILL.md",
        "---\nname: user-only\ndescription: x\ndisable-model-invocation: 'on'\n---\n\nbody\n",
    )
    entry = agent_skills.discover(tmp_path)[0]
    assert entry.model_invocable is False
    assert entry.user_invocable is True
    assert agent_skills.model_catalog([entry]) == ()


def test_user_invocation_recognises_only_the_users_own_gesture(tmp_path: Path):
    write(tmp_path, "market-research/SKILL.md", SKILL)
    entries = agent_skills.discover(tmp_path)
    assert agent_skills.user_invocations("请用 /market-research 分析") == ("market-research",)
    # A path or a fraction is not a gesture; an unknown name stays plain prose.
    assert agent_skills.user_invocations("/usr/bin and 5/8") == ()
    assert agent_skills.user_invocations("hi /nope-here") == ("nope-here",)
    assert agent_skills.load_user_skills(entries, "hi /nope-here") == ()
    assert [entry.name for entry in agent_skills.load_user_skills(entries, "/market-research")] == [
        "market-research"
    ]


def test_catalog_and_content_wrappers_match_upstream():
    entry = agent_skills.SkillEntry(
        name="market-research",
        description="Evidence-based market research.",
        when_to_use=None,
        body="Build the evidence pack first.",
        file="/skills/market-research/SKILL.md",
        resource_base="/skills/market-research",
        metadata={"legacy_slug": "market_research"},
    )
    catalog = agent_skills.render_catalog_message([entry])
    assert "<available_skills>" in catalog
    assert "- `market-research`: Evidence-based market research." in catalog
    content = agent_skills.render_skill_content(entry)
    assert content.startswith('<skill_content name="market-research">')
    assert "<skill_resources>/skills/market-research/SKILL.md</skill_resources>" in content
    assert "<skill_instructions>\nBuild the evidence pack first.\n</skill_instructions>" in content
    assert entry.legacy_slug == "market_research"


def test_the_packaged_catalog_is_valid_and_maps_back_to_the_registry():
    entries = agent_skills.discover(agent_skills.default_skills_dir())
    assert entries, "the packaged apps/api/skills directory must ship skills"
    assert all(entry.legacy_slug for entry in entries), "every migrated skill keeps its registry slug"
    assert all(agent_skills.SKILL_NAME_RE.match(entry.name) for entry in entries)
