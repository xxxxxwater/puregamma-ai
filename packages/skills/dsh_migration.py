from __future__ import annotations

import re
from dataclasses import dataclass

LEGACY_TO_DSH_SKILL_NAME = {
    "market_research": "market-research",
    "news_research": "news-research",
    "portfolio_review": "portfolio-review",
    "options_analysis": "options-analysis",
    "source_check": "source-check",
    "deep_research": "deep-research",
    "harness_deep_research": "harness-deep-research",
}

_DSH_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class DshSkillMigrationRef:
    legacy_slug: str
    dsh_name: str


def legacy_slug_to_dsh_name(slug: str) -> str:
    """Map a legacy PureGamma slug to DSH's kebab-case skill grammar.

    This is deliberately pure. It never touches the production database,
    installations, SkillRun history, or the filesystem.
    """
    normalized = (slug or "").strip().lower()
    if normalized in LEGACY_TO_DSH_SKILL_NAME:
        return LEGACY_TO_DSH_SKILL_NAME[normalized]
    candidate = normalized.replace("_", "-")
    if not _DSH_NAME.fullmatch(candidate):
        raise ValueError(
            f"legacy skill slug cannot be represented as a DSH skill name: {slug!r}"
        )
    return candidate


def migration_catalog() -> tuple[DshSkillMigrationRef, ...]:
    return tuple(
        DshSkillMigrationRef(legacy_slug=legacy, dsh_name=dsh)
        for legacy, dsh in sorted(LEGACY_TO_DSH_SKILL_NAME.items())
    )
