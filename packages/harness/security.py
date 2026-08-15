"""Harness capability contract: the only tools that may ever be exposed to
the research model, and the capabilities that are unconditionally denied.

The runner and the Research Gateway both enforce this list. Denials are
hard-coded here so no model prompt, plugin, or configuration can widen the
surface: Harness is a researcher, never an executor.
"""

from __future__ import annotations

# Phase-1 model tools exposed through the Research Gateway. Each one is
# implemented by an existing, audited PureGamma service (evidence, data,
# options, backtest lab, research runner, portfolio, artifacts).
ALLOWED_GATEWAY_TOOLS: tuple[str, ...] = (
    "get_evidence_snapshot",
    "get_market_series",
    "get_options_context",
    "run_backtest",
    "run_research_code",
    "get_portfolio_snapshot",
    "save_research_artifact",
)

# Capabilities that must never be reachable from Harness code, prompts,
# plugins, or the gateway. The gateway rejects tool names matching any of
# these; the runner image additionally lacks the binaries for them.
DENIED_HARNESS_CAPABILITIES: tuple[str, ...] = (
    "shell",
    "bash",
    "filesystem",
    "editor",
    "url_fetch",
    "browser",
    "sql",
    "graphql",
    "rpc",
    "env_read",
    "secret",
    "docker",
    "process_spawn",
    "order",
    "strategy_mutation",
    "risk_policy_mutation",
    "mandate_mutation",
    "kill_switch",
    "account_connect",
    "withdraw",
    "transfer",
    "payment",
    "direct_message",
)

DENIED_TOOL_NAME_SUBSTRINGS: tuple[str, ...] = (
    "bash",
    "shell",
    "exec",
    "run_command",
    "write_file",
    "edit_file",
    "read_file_host",
    "fetch_url",
    "http_request",
    "sql",
    "docker",
    "env",
    "secret",
    "order",
    "trade",
    "withdraw",
    "transfer",
    "kill",
    "mandate",
    "risk_policy",
)


def assert_tool_allowed(tool_name: str, extra_allowlist: tuple[str, ...] = ()) -> str:
    """Return ``tool_name`` if allowed; raise ``ValueError`` otherwise.

    ``extra_allowlist`` is a run-scoped narrowing list (e.g. from a capability
    token). It can only RESTRICT the global allowlist, never widen it:

    - every entry of ``extra_allowlist`` must itself be in
      ``ALLOWED_GATEWAY_TOOLS``, otherwise it is rejected outright;
    - the final allowed set is the INTERSECTION of the global allowlist and
      the extra allowlist.

    With no ``extra_allowlist`` provided, the global allowlist applies.
    """
    if tool_name in DENIED_HARNESS_CAPABILITIES:
        raise ValueError(f"denied capability: {tool_name}")
    lowered = tool_name.lower()
    for fragment in DENIED_TOOL_NAME_SUBSTRINGS:
        if fragment in lowered:
            raise ValueError(f"tool name matches denied pattern '{fragment}': {tool_name}")
    if tool_name not in ALLOWED_GATEWAY_TOOLS:
        raise ValueError(f"tool not in gateway allowlist: {tool_name}")
    if extra_allowlist:
        unknown = set(extra_allowlist) - set(ALLOWED_GATEWAY_TOOLS)
        if unknown:
            raise ValueError(
                "extra allowlist must be a subset of the global gateway allowlist: "
                + ", ".join(sorted(unknown))
            )
        if tool_name not in extra_allowlist:
            raise ValueError(f"tool not in run-scoped allowlist: {tool_name}")
    return tool_name
