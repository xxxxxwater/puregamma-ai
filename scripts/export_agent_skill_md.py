#!/usr/bin/env python3
"""Export PureGamma's built-in skills as DeepSeek Harness ``SKILL.md`` bundles.

The agent chat used to resolve skills through ``packages.skills.SkillRegistry``.
It now uses the DeepSeek Harness default design (``dsh-v0.1.7-rc.1``): skills are
directories with a ``SKILL.md`` whose YAML frontmatter carries ``name`` and
``description``.  This script performs that migration **from the existing
manifests**, so a built-in skill's instructions and data expectations are
carried over verbatim instead of being rewritten by hand.

Idempotent and re-runnable: it rewrites the same files from the same source, and
a target whose content already matches is left untouched.

    python3 scripts/export_agent_skill_md.py            # write
    python3 scripts/export_agent_skill_md.py --check     # report only

Upstream notes that shape the output:

* ``name`` must be kebab-case (``^[a-z0-9]+(?:-[a-z0-9]+)*$``), so the legacy
  underscore slugs become ``market-research`` and friends.  The original slug is
  kept in ``metadata.legacy_slug`` so ``skill_runs`` rows stay reconcilable.
* ``description`` is required; ``whenToUse`` is optional and only rendered when
  the manifest actually has something useful to say.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILTINS = REPO_ROOT / "packages" / "skills" / "builtins.py"
TARGET_ROOT = REPO_ROOT / "apps" / "api" / "skills"


def _literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def read_builtins(path: Path) -> list[dict]:
    """Every ``_manifest(...)`` call in BUILTIN_SKILLS, as plain data."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    entries: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "BUILTIN_SKILLS" for t in node.targets):
            continue
        if not isinstance(node.value, ast.List):
            continue
        for call in node.value.elts:
            if not isinstance(call, ast.Call):
                continue
            positional = [_literal(arg) for arg in call.args]
            keywords = {
                kw.arg: _literal(kw.value) for kw in call.keywords if kw.arg is not None
            }
            if len(positional) < 3 or not all(isinstance(v, str) for v in positional[:3]):
                continue
            slug, name, description = positional[0], positional[1], positional[2]
            entries.append(
                {
                    "slug": slug,
                    "name": name,
                    "description": description,
                    "prompt": keywords.get("prompt") or "",
                    "sources": keywords.get("sources") or [],
                    "tools": keywords.get("tools") or [],
                    "version": keywords.get("version") or "1.0.0",
                    "risk": keywords.get("risk") or "low",
                }
            )
    return entries


def kebab(slug: str) -> str:
    return slug.replace("_", "-").strip("-").lower()


def render(entry: dict) -> str:
    name = kebab(entry["slug"])
    if not name or any(part == "" for part in name.split("-")):
        raise SystemExit(f"slug {entry['slug']!r} cannot be expressed as a kebab-case skill name")
    when = (
        f"Use when the user asks for {entry['description'].rstrip('.').lower()} "
        "and the request should be answered from synchronized evidence rather than model memory."
    )
    tools = ", ".join(entry["tools"]) or "none"
    sources = ", ".join(entry["sources"]) or "none"
    body = [
        entry["prompt"].strip(),
        "",
        "## Authorized data sources",
        "",
        sources,
        "",
        "## Expected tools",
        "",
        tools,
        "",
        "## Boundaries",
        "",
        "- Loading this skill grants no data source, tool or permission by itself; the",
        "  server still applies entitlement, quota, billing and the tool allowlist of",
        "  the running agent.",
        "- Never fabricate a value, a citation or a timestamp. Report an unavailable",
        "  provider and deliver the best partial answer with its evidence gaps.",
    ]
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {entry['description']}\n"
        "whenToUse: >-\n"
        f"  {when}\n"
        "metadata:\n"
        f"  legacy_slug: {entry['slug']}\n"
        f"  publisher: PureGamma AI\n"
        f"  version: \"{entry['version']}\"\n"
        f"  risk_level: {entry['risk']}\n"
        "  migrated_from: packages/skills/builtins.py\n"
        "---\n"
        "\n" + "\n".join(body).rstrip() + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift, write nothing")
    args = parser.parse_args()

    entries = read_builtins(BUILTINS)
    if not entries:
        print("no built-in skills found; refusing to write nothing", file=sys.stderr)
        return 1

    drift = 0
    for entry in entries:
        target = TARGET_ROOT / kebab(entry["slug"]) / "SKILL.md"
        rendered = render(entry)
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current == rendered:
            print(f"[ok]    {target.relative_to(REPO_ROOT)}")
            continue
        drift += 1
        if args.check:
            print(f"[drift] {target.relative_to(REPO_ROOT)}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print(f"[write] {target.relative_to(REPO_ROOT)}")
    if args.check and drift:
        return 1
    print(f"\n{len(entries)} skills, {drift} changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
