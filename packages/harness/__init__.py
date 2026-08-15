"""DeepSeek Harness integration primitives.

This package contains ONLY trusted, control-plane-side code:

- pinned versions and integrity hashes (``versions``),
- the tool allowlist / denied-capability contract (``security``),
- the minimal Cordis composition definition (``composition``),
- the idempotent research-run state machine (``state_machine``),
- the adapter protocol plus a deterministic offline mock (``adapter``).

The low-trust harness-runner subprocess is NOT started from this package
directly in production; Phase 2 wires it behind a dedicated isolated runner
service with a separate Celery orchestrator worker. The mock adapter exists
so CI and local development never need a real DeepSeek key or binary.
"""

from packages.harness.adapter import HarnessAdapter, MockHarnessAdapter
from packages.harness.composition import (
    JSON_RPC_TOOL,
    MINIMAL_CORDIS_COMPOSITION,
)
from packages.harness.security import (
    ALLOWED_GATEWAY_TOOLS,
    DENIED_HARNESS_CAPABILITIES,
    assert_tool_allowed,
)
from packages.harness.state_machine import (
    ALLOWED_TRANSITIONS,
    HARNESS_RUN_STATES,
    IllegalStateTransition,
    TERMINAL_STATES,
    transition_run,
)
from packages.harness.versions import (
    PINNED_HARNESS_VERSIONS,
    HarnessVersions,
    compute_input_hash,
)

__all__ = [
    "ALLOWED_GATEWAY_TOOLS",
    "ALLOWED_TRANSITIONS",
    "DENIED_HARNESS_CAPABILITIES",
    "HARNESS_RUN_STATES",
    "HarnessAdapter",
    "HarnessVersions",
    "IllegalStateTransition",
    "JSON_RPC_TOOL",
    "MINIMAL_CORDIS_COMPOSITION",
    "MockHarnessAdapter",
    "PINNED_HARNESS_VERSIONS",
    "TERMINAL_STATES",
    "assert_tool_allowed",
    "compute_input_hash",
    "transition_run",
]
