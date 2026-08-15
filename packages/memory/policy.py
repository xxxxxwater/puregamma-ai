"""Memory Policy: namespace rules, sensitivity, auto-accept matrix, TTL,
secret detection, and the hard rule that memory is never trading input."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

MEMORY_NAMESPACES: frozenset[str] = frozenset(
    {"chat", "secretary", "research", "portfolio", "trading"}
)

# The trading namespace is read-only by policy. Trading decisions, risk
# limits, mandate state and order permissions are NEVER derived from memory.
WRITE_DISABLED_NAMESPACES: frozenset[str] = frozenset({"trading"})

SENSITIVE_LABELS: frozenset[str] = frozenset(
    {"api_key", "private_key", "payment_info", "account_credential", "identity_document"}
)

# Never-allow content patterns (keys, seeds, private keys, card numbers,
# bearer tokens, connection strings). Detection force-rejects the proposal.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),                       # OpenAI-style keys
    re.compile(r"pk_(live|test)_[A-Za-z0-9]{10,}"),             # Stripe keys
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"0x[0-9a-fA-F]{64}"),                           # raw secp256k1 keys
    re.compile(r"\b\d{13,19}\b"),                               # card / long account numbers
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"(postgres|postgresql|redis|amqp|mongodb)://[^\s\"']+@"),  # connection strings
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),                    # long base64 blobs
    re.compile(r"AKIA[0-9A-Z]{16}"),                            # AWS access keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),                  # GitHub tokens
)


def detect_secrets(text: str) -> list[str]:
    """Return the matched secret fragments (truncated) found in ``text``."""
    found: list[str] = []
    for pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            fragment = match.group(0)
            found.append(fragment[:24] + ("..." if len(fragment) > 24 else ""))
    return found


def redact_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def content_hash(content: dict[str, Any]) -> str:
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryDecision:
    action: str  # auto_accept | pending | reject
    reason: str
    ttl_seconds: int | None


class MemoryPolicy:
    """Decides whether a MemoryProposal is auto-accepted, needs user consent,
    or is rejected. All defaults are conservative (fail closed)."""

    def __init__(self, *, auto_accept_low_risk: bool = True) -> None:
        self.auto_accept_low_risk = auto_accept_low_risk

    def decide(
        self,
        *,
        namespace: str,
        kind: str,
        content: dict[str, Any],
        proposed_ttl_seconds: int | None,
    ) -> MemoryDecision:
        if namespace not in MEMORY_NAMESPACES:
            return MemoryDecision("reject", f"unknown namespace: {namespace}", None)
        if namespace in WRITE_DISABLED_NAMESPACES:
            return MemoryDecision(
                "reject",
                f"namespace '{namespace}' is read-only; memory can never be trading input",
                None,
            )

        text = json.dumps(content, ensure_ascii=True)
        secrets = detect_secrets(text)
        if secrets:
            return MemoryDecision(
                "reject",
                "content matched a secret pattern: " + ", ".join(secrets),
                None,
            )

        ttl = self._default_ttl(namespace, kind, proposed_ttl_seconds)
        if kind in _AUTO_ACCEPT_KINDS and self.auto_accept_low_risk:
            return MemoryDecision("auto_accept", "low-risk deterministic kind", ttl)
        return MemoryDecision("pending", "requires user confirmation", ttl)

    def _default_ttl(self, namespace: str, kind: str, proposed: int | None) -> int | None:
        if proposed is not None and proposed >= 0:
            return proposed
        days = _DEFAULT_TTL_DAYS.get(kind)
        if days is None:
            return None  # long-lived
        return int(timedelta(days=days).total_seconds())


# Auto-accept only applies to low-risk deterministic kinds. Watchlists,
# conclusions and todos always require user confirmation (or explicit
# low-risk auto-accept for conclusions per policy review).
_AUTO_ACCEPT_KINDS: frozenset[str] = frozenset(
    {
        "language_preference",
        "display_preference",
        "research_task_incomplete",
    }
)

# Default TTL (days) for kinds that expire. None means long-lived (user-managed).
_DEFAULT_TTL_DAYS: dict[str, int | None] = {
    "conversation_summary": 30,
    "language_preference": None,
    "display_preference": None,
    "watchlist": None,
    "research_task_incomplete": 30,
    "deep_research_conclusion_summary": 30,
    "secretary_todo": None,
}
