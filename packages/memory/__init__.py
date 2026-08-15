"""PureGamma-owned Memory Service.

Models and Harness NEVER write user memory directly. Every write flows
through: Memory Proposal -> server-side Memory Policy -> user confirmation
or low-risk auto-accept -> immutable audit record -> structured write.

Memory is untrusted context: it can never override system policy, Skill
permissions, Evidence Packs, risk limits, or trading boundaries. The
``trading`` namespace rejects writes entirely.
"""

from packages.memory.policy import (
    MEMORY_NAMESPACES,
    WRITE_DISABLED_NAMESPACES,
    MemoryDecision,
    MemoryPolicy,
    detect_secrets,
    redact_secrets,
)
from packages.memory.service import MemoryService

__all__ = [
    "MEMORY_NAMESPACES",
    "WRITE_DISABLED_NAMESPACES",
    "MemoryDecision",
    "MemoryPolicy",
    "MemoryService",
    "detect_secrets",
    "redact_secrets",
]
