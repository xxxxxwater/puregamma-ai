"""Evidence Pack contract shared by Agent, Skills, reports, and automations."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


EVIDENCE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class EvidenceRequirement:
    kind: str
    minimum: int = 1


@dataclass
class EvidenceRecord:
    tool: str
    kind: str
    summary: str
    data: Any
    provider_count: int = 0
    source_count: int = 0


@dataclass
class EvidencePack:
    requirements: list[EvidenceRequirement]
    records: list[EvidenceRecord] = field(default_factory=list)

    def add_tool_result(self, result: Any) -> None:
        tool_name = str(getattr(result, "tool_name", "unknown"))
        data = getattr(result, "data", None)
        sources = list(getattr(result, "sources", []) or [])
        kind = _kind_for_tool(tool_name)
        providers = {str(getattr(source, "provider", "unknown")) for source in sources}
        self.records.append(EvidenceRecord(
            tool=tool_name,
            kind=kind,
            summary=str(getattr(result, "summary", ""))[:1_000],
            data=data,
            provider_count=len(providers),
            source_count=len(sources),
        ))

    def count(self, kind: str) -> int:
        return sum(_record_quantity(record) for record in self.records if record.kind == kind)

    @property
    def missing(self) -> list[str]:
        return [item.kind for item in self.requirements if self.count(item.kind) < item.minimum]

    @property
    def sufficient(self) -> bool:
        return not self.missing

    def public_summary(self) -> dict[str, Any]:
        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "sufficient": self.sufficient,
            "missing": self.missing,
            "record_count": len(self.records),
            "source_count": sum(record.source_count for record in self.records),
            "provider_count": sum(record.provider_count for record in self.records),
            "kinds": sorted({record.kind for record in self.records}),
        }

    def model_payload(self, *, portfolio_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "quality": self.public_summary(),
            "requirements": [asdict(item) for item in self.requirements],
            "records": [asdict(record) for record in self.records],
            "portfolio_context": portfolio_context,
        }


def requirements_for(intent: str, skill_slugs: list[str], assets: list[str]) -> list[EvidenceRequirement]:
    selected = set(skill_slugs)
    requirements: list[EvidenceRequirement] = []
    if intent == "market_research" or "market_research" in selected:
        requirements.extend((EvidenceRequirement("market_quote"), EvidenceRequirement("source_document")))
    if intent in {"news_research", "source_check"} or selected.intersection({"news_research", "source_check"}):
        requirements.append(EvidenceRequirement("source_document"))
    if intent == "portfolio_review" or "portfolio_review" in selected:
        requirements.append(EvidenceRequirement("portfolio_snapshot"))
    if intent == "options_analysis" or "options_analysis" in selected:
        requirements.append(EvidenceRequirement("options_snapshot"))
    if intent == "deep_research" or "deep_research" in selected:
        requirements.append(EvidenceRequirement("source_document"))
        if assets:
            requirements.append(EvidenceRequirement("market_quote"))
    unique: dict[str, EvidenceRequirement] = {item.kind: item for item in requirements}
    return list(unique.values())


def _kind_for_tool(tool_name: str) -> str:
    if tool_name in {"get_market_quote", "get_market_history"}:
        return "market_quote"
    if tool_name in {"get_recent_news", "search_news", "search_source_documents", "get_sentiment_context"}:
        return "source_document"
    if tool_name in {"get_account_snapshot", "get_position_snapshot", "get_open_orders"}:
        return "portfolio_snapshot"
    if tool_name in {"get_options_context", "get_earnings_gamma"}:
        return "options_snapshot"
    if tool_name == "get_data_source_status":
        return "provider_status"
    if "backtest" in tool_name or "strategy_performance" in tool_name:
        return "strategy_result"
    return "tool_result"


def _record_quantity(record: EvidenceRecord) -> int:
    data = record.data
    if not data:
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("count", "quoteCount", "documentCount", "candidateCount"):
            if key in data:
                try:
                    return max(0, int(data[key]))
                except (TypeError, ValueError):
                    return 0
    return 1


def _providers(data: Any) -> set[str]:
    if not isinstance(data, dict):
        return set()
    values: set[str] = set()
    if data.get("provider"):
        values.add(str(data["provider"]))
    for key in ("quotes", "documents", "items", "sources"):
        rows = data.get(key)
        if isinstance(rows, list):
            values.update(str(row.get("provider")) for row in rows if isinstance(row, dict) and row.get("provider"))
    return values
