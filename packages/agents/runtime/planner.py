from __future__ import annotations

from dataclasses import asdict, dataclass

from packages.data.evidence import requirements_for
from packages.data.lexicon import LEXICON_VERSION, understand_query


RUNTIME_PLAN_VERSION = "1.0"


@dataclass(frozen=True)
class AgentPlan:
    intent: str
    goal: str
    assets: tuple[str, ...]
    horizon: str | None
    skill_slugs: tuple[str, ...]
    data_sources: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    clarification_recommended: bool
    clarification_fields: tuple[str, ...]
    next_actions: tuple[str, ...]
    confidence: float

    def as_dict(self) -> dict:
        return {
            **asdict(self),
            "assets": list(self.assets),
            "skill_slugs": list(self.skill_slugs),
            "data_sources": list(self.data_sources),
            "evidence_requirements": list(self.evidence_requirements),
            "clarification_fields": list(self.clarification_fields),
            "next_actions": list(self.next_actions),
            "runtime_plan_version": RUNTIME_PLAN_VERSION,
            "lexicon_version": LEXICON_VERSION,
        }


_INTENT_SKILLS = {
    "market_research": ("market_research",),
    "news_research": ("news_research",),
    "portfolio_review": ("portfolio_review",),
    "options_analysis": ("options_analysis",),
    "source_check": ("source_check",),
    "deep_research": ("deep_research",),
}

_INTENT_SOURCES = {
    "market_research": ("market", "rss"),
    "news_research": ("rss",),
    "portfolio_review": ("portfolio", "market"),
    "options_analysis": ("options", "market"),
    "source_check": ("rss",),
    "deep_research": ("market", "rss"),
}

_NEXT_ACTIONS = {
    "market_research": ("compare_changes", "set_watch", "review_risk"),
    "news_research": ("track_catalyst", "compare_sources", "set_watch"),
    "portfolio_review": ("stress_test", "review_concentration", "schedule_brief"),
    "options_analysis": ("compare_expiries", "review_liquidity", "save_research"),
    "strategy_backtest": ("adjust_assumptions", "compare_periods", "paper_preview"),
    "general_research": ("deepen_research", "save_research"),
}


def plan_agent_request(
    query: str,
    *,
    requested_skill_slugs: list[str] | None = None,
    requested_data_sources: list[str] | None = None,
) -> AgentPlan:
    understanding = understand_query(query)
    explicit_skills = tuple(dict.fromkeys(requested_skill_slugs or []))
    skills = explicit_skills or _INTENT_SKILLS.get(understanding.intent, ())
    explicit_sources = tuple(dict.fromkeys(requested_data_sources or []))
    sources = explicit_sources or _INTENT_SOURCES.get(understanding.intent, ())
    requirements = requirements_for(understanding.intent, list(skills), list(understanding.assets))
    goal = query.strip().replace("\n", " ")[:240]
    return AgentPlan(
        intent=understanding.intent,
        goal=goal,
        assets=understanding.assets,
        horizon=understanding.horizon,
        skill_slugs=skills,
        data_sources=sources,
        evidence_requirements=tuple(item.kind for item in requirements),
        clarification_recommended=bool(understanding.ambiguity and not explicit_skills and understanding.intent != "general_research"),
        clarification_fields=understanding.ambiguity,
        next_actions=_NEXT_ACTIONS.get(understanding.intent, _NEXT_ACTIONS["general_research"]),
        confidence=understanding.confidence,
    )
