"""Harness adapter protocol and the deterministic offline mock.

Phase 2 introduces the real runner adapter (JSON-RPC to the isolated
runner container). The mock below is the ONLY sanctioned executor until
then, and remains the CI adapter forever: it needs no DeepSeek key, no
network, and no runtime binary, and it produces reproducible traces.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from packages.harness.security import ALLOWED_GATEWAY_TOOLS, assert_tool_allowed


@dataclass(frozen=True)
class ToolCallTrace:
    tool_name: str
    arguments: dict[str, Any]
    result_summary: str
    credits_used: int


@dataclass(frozen=True)
class HarnessRunResult:
    """Output of one completed (mock or real) research run."""

    status: str  # completed | degraded | failed | canceled | timed_out
    structured: dict[str, Any]
    markdown: str
    citations: list[dict[str, Any]]
    methodology: str
    assumptions: list[str]
    limitations: list[str]
    tool_traces: list[ToolCallTrace]
    usage: dict[str, int]
    error_code: str | None = None


class HarnessAdapter(Protocol):
    def start_run(
        self,
        *,
        run_id: str,
        user_id: str,
        goal_summary: str,
        evidence: dict[str, Any],
        allowed_tools: tuple[str, ...],
        budget_credits: int,
        timeout_seconds: int,
        session_id: str,
    ) -> None: ...

    def cancel_run(self, run_id: str) -> None: ...

    def poll_result(self, run_id: str) -> HarnessRunResult | None: ...


class MockHarnessAdapter:
    """Deterministic, offline Harness simulation for dev/CI.

    - plans a small multi-step research graph derived from the goal,
    - only ever calls tools present in ``allowed_tools`` (which the caller
      must derive from ALLOWED_GATEWAY_TOOLS),
    - never calls shell/filesystem/network/order tools (enforced via
      ``assert_tool_allowed``),
    - emits a bounded token usage derived from input size,
    - returns a structured ResearchArtifact-shaped result.
    """

    name = "mock-harness"

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._canceled: set[str] = set()

    def start_run(
        self,
        *,
        run_id: str,
        user_id: str,
        goal_summary: str,
        evidence: dict[str, Any],
        allowed_tools: tuple[str, ...],
        budget_credits: int,
        timeout_seconds: int,
        session_id: str,
    ) -> None:
        for tool in allowed_tools:
            assert_tool_allowed(tool)  # mock can never widen the contract
        self._runs[run_id] = {
            "goal": goal_summary,
            "user_id": user_id,
            "evidence": evidence,
            "allowed_tools": tuple(allowed_tools),
            "budget_credits": budget_credits,
            "timeout_seconds": timeout_seconds,
            "session_id": session_id,
            "credits_spent": 0,
        }

    def cancel_run(self, run_id: str) -> None:
        self._canceled.add(run_id)

    def poll_result(self, run_id: str) -> HarnessRunResult | None:
        run = self._runs.get(run_id)
        if run is None:
            return None
        if run_id in self._canceled:
            return HarnessRunResult(
                status="canceled",
                structured={},
                markdown="",
                citations=[],
                methodology="",
                assumptions=[],
                limitations=[],
                tool_traces=[],
                usage={"input_tokens": 0, "output_tokens": 0, "tool_calls": 0},
                error_code="CANCELED",
            )

        tools = run["allowed_tools"]
        goal = run["goal"]
        traces: list[ToolCallTrace] = []

        if "get_evidence_snapshot" in tools:
            evidence_items = run["evidence"].get("items", [])
            traces.append(
                ToolCallTrace(
                    tool_name="get_evidence_snapshot",
                    arguments={"scope": "run"},
                    result_summary=f"frozen evidence returned ({len(evidence_items)} items)",
                    credits_used=1,
                )
            )
        if "get_market_series" in tools:
            traces.append(
                ToolCallTrace(
                    tool_name="get_market_series",
                    arguments={"symbols": ["BTC"], "timeframe": "1d"},
                    result_summary="archived market series returned",
                    credits_used=2,
                )
            )
        if "run_backtest" in tools:
            traces.append(
                ToolCallTrace(
                    tool_name="run_backtest",
                    arguments={"strategy_spec_ref": "approved-spec"},
                    result_summary="artifact reference returned (no file paths)",
                    credits_used=5,
                )
            )
        if "get_options_context" in tools:
            traces.append(
                ToolCallTrace(
                    tool_name="get_options_context",
                    arguments={"asset": "BTC"},
                    result_summary="read-only options surface returned",
                    credits_used=2,
                )
            )
        if "get_portfolio_snapshot" in tools:
            traces.append(
                ToolCallTrace(
                    tool_name="get_portfolio_snapshot",
                    arguments={"sanitized": True},
                    result_summary="sanitized portfolio snapshot returned",
                    credits_used=1,
                )
            )
        if "save_research_artifact" in tools:
            traces.append(
                ToolCallTrace(
                    tool_name="save_research_artifact",
                    arguments={"schema": "research_artifact/1.0"},
                    result_summary="artifact staged for server validation",
                    credits_used=1,
                )
            )

        input_tokens = 64 + min(4000, len(goal) * 4)
        output_tokens = 256 + len(traces) * 96
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tool_calls": len(traces),
            "credits_used": sum(t.credits_used for t in traces),
        }

        citations = [
            {
                "provider": "mock",
                "source_id": item.get("source_id", "mock-source"),
                "source_url": item.get("source_url"),
                "source_timestamp": item.get("source_timestamp"),
            }
            for item in run["evidence"].get("items", [])[:5]
        ]

        structured = {
            "goal": goal,
            "findings": [f"mock finding {i + 1} for: {goal[:80]}" for i in range(3)],
            "recommended_actions": ["verify against live evidence before use"],
        }
        markdown = (
            "## Mock research result\n\n"
            + "\n".join(f"- {f}" for f in structured["findings"])
            + "\n\n> This is a deterministic mock run; no model was invoked."
        )

        return HarnessRunResult(
            status="completed",
            structured=structured,
            markdown=markdown,
            citations=citations,
            methodology="deterministic mock plan: evidence -> series -> backtest -> artifact",
            assumptions=["mock market data"],
            limitations=["mock adapter used; treat all findings as illustrative"],
            tool_traces=traces,
            usage=usage,
        )


def artifact_content_hash(structured: dict[str, Any], markdown: str, citations: list[dict[str, Any]]) -> str:
    """Server-side content hash for a ResearchArtifact payload."""
    payload = json.dumps(
        {"structured": structured, "markdown": markdown, "citations": citations},
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
