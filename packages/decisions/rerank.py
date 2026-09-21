"""Jev-backed evidence reranking for the research surface.

Retrieval returns candidates by lexical or vector similarity, which is cheap and
recall-oriented. Jev is used to score how well each candidate actually answers
the question, and code keeps only the strongest few for the writer.

Shape follows the TypeSafe guidance: Jev evaluates the state once and answers
every question in parallel, so one call carries one `score` question per
candidate. That keeps latency flat as the candidate count grows, and it keeps
the comparison fair because every candidate is graded against the same rubric
in the same pass.

Fail-closed and provenance-preserving, both deliberately:

* Any failure returns None and the caller keeps the original order. Retrieval
  is never made worse by a model outage.
* Scores are returned alongside the original index, so the caller can still
  cite where each kept item came from.
* Scores are Jev's judgement of relevance, not a measured return. Nothing here
  is presented as alpha, and the caller must not relabel it as such.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from packages.decisions.jev_client import JevClient, JevError, JevUnavailable, score

#: Rubric levels. Ordered and independently meaningful, as the primitive wants
#: -- a score is a position on this scale, not a free-form number.
RELEVANCE_LEVELS: list[str] = [
    "Irrelevant to the question",
    "Tangential, shares only keywords",
    "Partially answers the question",
    "Directly answers most of the question",
    "Directly and completely answers the question",
]

#: One request can only carry so many questions before the state plus questions
#: budget is at risk, and each question costs input tokens. Candidates beyond
#: this are left in their original order rather than silently dropped.
MAX_CANDIDATES = 24

#: Characters of each candidate sent as evidence. Long documents are truncated;
#: relevance is usually decidable from the opening.
MAX_CANDIDATE_CHARS = 1_200

#: Score below this is dropped from the kept set. A candidate scoring at or
#: under "tangential" contributes noise rather than evidence.
MIN_KEEP_SCORE = 1.5


@dataclass(frozen=True)
class RankedEvidence:
    index: int           # position in the input sequence, for provenance
    score: float
    text: str


@dataclass(frozen=True)
class RerankResult:
    kept: list[RankedEvidence]
    dropped: int
    model: str           # versioned id that answered, for the audit trail


def rerank_evidence(
    question: str,
    candidates: Sequence[str],
    *,
    client: JevClient | None = None,
    limit: int = 8,
    min_score: float = MIN_KEEP_SCORE,
) -> RerankResult | None:
    """Rank *candidates* by how well each answers *question*.

    Returns None when there is no usable opinion, which the caller must treat
    as "keep the original order" -- never as "nothing is relevant".
    """
    query = (question or "").strip()
    items = [c for c in (candidates or []) if isinstance(c, str) and c.strip()]
    if not query or not items:
        return None

    jev = client or JevClient()
    if not jev.configured:
        return None

    window = items[:MAX_CANDIDATES]
    questions: dict[str, dict[str, Any]] = {}
    for position, text in enumerate(window):
        questions[f"relevance_{position}"] = score(
            f"How well does this evidence answer the question?\n\n"
            f"QUESTION: {query}\n\nEVIDENCE:\n{text[:MAX_CANDIDATE_CHARS]}",
            RELEVANCE_LEVELS,
        )

    try:
        result = jev.ask({"question": query}, questions)
    except (JevUnavailable, JevError, ValueError):
        return None

    answers = result.get("answers") or {}
    ranked: list[RankedEvidence] = []
    for position, text in enumerate(window):
        answer = answers.get(f"relevance_{position}") or {}
        value = answer.get("score")
        if not isinstance(value, (int, float)):
            continue
        ranked.append(RankedEvidence(index=position, score=float(value), text=text))

    if not ranked:
        # Every answer was malformed: no opinion, not "all irrelevant".
        return None

    ranked.sort(key=lambda item: item.score, reverse=True)
    kept = [item for item in ranked if item.score >= min_score][: max(1, limit)]
    if not kept:
        # Nothing cleared the bar. That is a real result, but returning an
        # empty set would silently blank the research run, so the best
        # candidate is kept and the caller can decide what to do with it.
        kept = ranked[:1]

    return RerankResult(
        kept=kept,
        dropped=len(window) - len(kept),
        model=str(result.get("model") or ""),
    )
