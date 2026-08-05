"""Static AST validation for user research code.

The validator runs before any container is spawned. Imports are restricted to
the Python standard library plus numpy/pandas, minus an explicit blocklist of
network/process/destructive modules. Dangerous dynamic-execution builtins and
destructive ``os`` calls are rejected as well. This is a defense-in-depth
filter; the hard isolation boundary is the ephemeral container itself
(no network, read-only root filesystem, resource caps).
"""

from __future__ import annotations

import ast
import sys

# Third-party libraries allowed in addition to the standard library. These
# must exist in the runner image (see Dockerfile.runner); matplotlib is pinned
# to the Agg backend by the wrapper env (MPLCONFIGDIR=/tmp, no display).
ALLOWED_THIRD_PARTY = {"numpy", "pandas", "matplotlib"}

# Modules that are never allowed, even though they live in the stdlib.
BLOCKED_MODULES = {
    # networking / data exfiltration
    "socket",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "http",
    "ftplib",
    "telnetlib",
    "smtplib",
    "imaplib",
    "poplib",
    "nntplib",
    "xmlrpc",
    "webbrowser",
    # process execution / escape hatches
    "subprocess",
    "multiprocessing",
    "concurrent",
    "asyncio",
    "ctypes",
    "_ctypes",
    "signal",
    "pty",
    "ensurepip",
    "pip",
    "venv",
    # destructive filesystem helpers (os restricted usage stays allowed)
    "shutil",
}

BLOCKED_CALLS = {"eval", "exec", "compile", "__import__", "input", "breakpoint", "exit", "quit"}

# os attributes that must not be called (restricted os usage is otherwise fine).
BLOCKED_OS_ATTRIBUTES = {
    "system",
    "popen",
    "fork",
    "forkpty",
    "kill",
    "killpg",
    "remove",
    "unlink",
    "rmdir",
    "removedirs",
    "rename",
    "renames",
    "replace",
    "chmod",
    "chown",
    "chroot",
    "symlink",
    "link",
    "mknod",
    "mkfifo",
}


class CodeValidationError(ValueError):
    """Raised when user research code fails the static safety check."""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("research code rejected: " + "; ".join(violations))


def _allowed_module(root: str) -> bool:
    if root in BLOCKED_MODULES:
        return False
    if root in ALLOWED_THIRD_PARTY:
        return True
    return root in sys.stdlib_module_names


def find_violations(code: str) -> list[str]:
    """Return a list of human-readable policy violations in ``code``."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: {exc}"]
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if not _allowed_module(root):
                    violations.append(f"import of '{alias.name}' is not allowed")
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                root = node.module.split(".")[0]
                if not _allowed_module(root):
                    violations.append(f"import from '{node.module}' is not allowed")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BLOCKED_CALLS:
                violations.append(f"call to '{func.id}()' is not allowed")
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "os" and (
                    func.attr in BLOCKED_OS_ATTRIBUTES
                    or func.attr.startswith(("spawn", "exec"))
                ):
                    violations.append(f"call to 'os.{func.attr}()' is not allowed")
    return violations


def validate_research_code(code: str) -> None:
    """Raise :class:`CodeValidationError` when the code is not allowed."""
    violations = find_violations(code)
    if violations:
        raise CodeValidationError(violations)
