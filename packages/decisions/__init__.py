"""Structured-decision helpers.

Deliberately separate from ``packages.agents.llm``: those providers are
*text-completion* abstractions that return prose. Jev evaluates typed questions
against a state and returns structured answers, so it supplies judgement to
code that still owns the wording -- intent routing and evidence reranking here,
rather than generating the reply itself.

Every entry point in this package is fail-closed: when Jev has no confident,
well-formed opinion it returns None and the caller keeps the behaviour it
already had.
"""
from packages.decisions.intent import INTENTS, IntentDecision, classify_intent
from packages.decisions.jev_client import (
    JevClient,
    JevError,
    JevUnavailable,
    choice,
    noul,
    score,
)
from packages.decisions.rerank import RankedEvidence, RerankResult, rerank_evidence

__all__ = [
    "INTENTS",
    "IntentDecision",
    "JevClient",
    "JevError",
    "JevUnavailable",
    "RankedEvidence",
    "RerankResult",
    "choice",
    "classify_intent",
    "noul",
    "rerank_evidence",
    "score",
]
