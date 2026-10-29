"""Every path a Harness legacy-api provider calls must exist on the FastAPI app.

The compatibility providers (harness/plugins/*-legacy-api) reach FastAPI
directly at PUREGAMMA_LEGACY_API_URL (http://127.0.0.1:8000 by default, no
reverse proxy in between). Routers mounted with ``prefix="/api"`` therefore
need the ``/api`` segment in the provider path; without it every call 404s and
the provider looks "unavailable" for a reason nobody can see in unit tests.
This guard resolves each provider path template against the real route table.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from apps.api.main import app

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = sorted((ROOT / "harness" / "plugins").glob("*-legacy-api/src/*.ts"))
# Quoted or template literals that start with a path segment.
LITERAL = re.compile(r"(?:'(/[a-z][^'\s]*)'|`(/[a-z][^`]*)`)")
INTERPOLATION = re.compile(r"\$\{(?:[^{}]|\{[^{}]*\})*\}")


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"^\s*//.*$", "", source, flags=re.M)


CHOICE = re.compile(r"\$\{[^{}]*\?\s*'([^']+)'\s*:\s*'([^']+)'\s*\}")


def _expand_choices(literal: str) -> list[str]:
    """`${cond ? 'pause' : 'resume'}` names two literal segments; check both."""
    match = CHOICE.search(literal)
    if match is None:
        return [literal]
    head, tail = literal[: match.start()], literal[match.end() :]
    return [variant for choice in match.groups() for variant in _expand_choices(head + choice + tail)]


def provider_paths() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for file in PROVIDERS:
        for match in LITERAL.finditer(_strip_comments(file.read_text(encoding="utf-8"))):
            literal = match.group(1) or match.group(2)
            # `${suffix}` glued to a segment is a query string, not a path segment.
            literal = re.sub(r"(?<=[A-Za-z0-9_-])" + INTERPOLATION.pattern, "", literal)
            for variant in _expand_choices(literal):
                template = INTERPOLATION.sub("{param}", variant).split("?", 1)[0]
                found.append((file.parent.parent.name, template))
    return sorted(set(found))


def route_patterns() -> list[re.Pattern[str]]:
    patterns = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if not isinstance(path, str):
            continue
        patterns.append(re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", re.escape(path).replace(r"\{", "{").replace(r"\}", "}")) + "$"))
    return patterns


ROUTES = route_patterns()
PATHS = provider_paths()


def test_the_guard_sees_every_provider() -> None:
    assert len(PROVIDERS) >= 15
    assert len(PATHS) >= 110


@pytest.mark.parametrize(("plugin", "path"), PATHS, ids=[f"{plugin}:{path}" for plugin, path in PATHS])
def test_provider_path_is_served_by_fastapi(plugin: str, path: str) -> None:
    probe = path.replace("{param}", "x")
    assert any(pattern.match(probe) for pattern in ROUTES), f"{plugin} calls {path}, which no FastAPI route serves"
