"""Pinned DeepSeek Harness versions and integrity hashes.

Every production run records these four values on ``HarnessResearchRun``
(harness_version, runtime_version, cordis_config_hash, plugin_lock_hash) so
any behavioral drift is auditable. The values below are PLACEHOLDER pins:
Phase 2 replaces them with the exact ``deepseek-harness-sdk`` and
``runtime-bin`` versions that ship in the runner image. Until then the mock
adapter is the only sanctioned executor and no real binary is downloaded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HarnessVersions:
    sdk_version: str
    runtime_bin_version: str
    cordis_config_hash: str
    plugin_lock_hash: str


# Placeholder pins: updated in Phase 2 when the real SDK/runtime-bin are
# vendored into the runner image. The mock adapter does not need them.
PINNED_HARNESS_VERSIONS = HarnessVersions(
    sdk_version="deepseek-harness-sdk==0.0.0-placeholder",
    runtime_bin_version="runtime-bin==0.0.0-placeholder",
    cordis_config_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
    plugin_lock_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
)


def compute_input_hash(
    goal_summary: str,
    *,
    evidence_snapshot_hash: str | None = None,
    skill_version: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Deterministic hash of everything that defines one research input.

    Used to dedupe identical deep-research requests and to prove that the
    runner consumed exactly the frozen evidence it was given.
    """
    payload = {
        "goal_summary": goal_summary,
        "evidence_snapshot_hash": evidence_snapshot_hash or "",
        "skill_version": skill_version or "",
        "extra": extra or {},
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
