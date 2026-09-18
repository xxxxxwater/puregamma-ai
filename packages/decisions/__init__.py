"""Structured-decision helpers.

Deliberately separate from ``packages.agents.llm``: those providers are
*text-completion* abstractions that return prose. Jev is a System One model
that evaluates typed questions against a state and returns structured answers.
Putting it behind ``LLMProvider`` would be a category error and would make it
selectable from every chat path in the product.
"""
from packages.decisions.jev_client import (
    JevClient,
    JevError,
    JevUnavailable,
    choice,
    noul,
    score,
)
from packages.decisions.redaction import (
    REDACTED_STATE_SCHEMA,
    assert_no_absolute_scale,
    book_shape,
    redact_account_view,
)

__all__ = [
    "JevClient",
    "JevError",
    "JevUnavailable",
    "REDACTED_STATE_SCHEMA",
    "assert_no_absolute_scale",
    "book_shape",
    "choice",
    "noul",
    "redact_account_view",
    "score",
]
