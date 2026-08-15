"""Minimal Cordis composition for the DeepSeek Harness runner.

The default Harness SDK composition enables Bash, file editing and the
``danger-full-access`` tool group — none of which may exist in production.
This module is the single source of truth for the reduced composition:

- JSON-RPC server stays enabled (Python SDK communication);
- the research tool surface is limited to the gateway client tool;
- bash / shell / editor / filesystem / network tools are explicitly absent.

The runner image (Phase 2) validates that its generated Cordis config hash
equals ``PINNED_HARNESS_VERSIONS.cordis_config_hash`` before accepting runs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from packages.harness.security import ALLOWED_GATEWAY_TOOLS

JSON_RPC_TOOL = "json_rpc_server"


@dataclass(frozen=True)
class CordisComposition:
    schema_version: str = "1.0"
    tools_enabled: tuple[str, ...] = (JSON_RPC_TOOL, "research_gateway_client")
    tools_disabled: tuple[str, ...] = (
        "bash",
        "shell",
        "filesystem",
        "editor",
        "write_file",
        "edit_file",
        "url_fetch",
        "browser",
        "danger-full-access",
    )
    plugins: tuple[str, ...] = ()
    allowed_gateway_tools: tuple[str, ...] = ALLOWED_GATEWAY_TOOLS
    network_enabled: bool = False
    env_inheritance: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)

    def config_hash(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "tools_enabled": list(self.tools_enabled),
            "tools_disabled": list(self.tools_disabled),
            "plugins": list(self.plugins),
            "allowed_gateway_tools": list(self.allowed_gateway_tools),
            "network_enabled": self.network_enabled,
            "env_inheritance": list(self.env_inheritance),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


MINIMAL_CORDIS_COMPOSITION = CordisComposition()
