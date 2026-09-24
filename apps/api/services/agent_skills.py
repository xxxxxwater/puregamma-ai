"""Agent skills, in the DeepSeek Harness default design.

Reference: DeepSeek Harness ``dsh-v0.1.7-rc.1``
(commit 46a7f68b0922371ce7144b668b90e377d8e799f4):

* ``packages/skill/skill-filesystem`` - discovery, on-disk format, frontmatter;
* ``packages/skill/skill`` - the registry and ``renderSkillContent()``;
* ``packages/skill/tool-skill`` - the ``skill`` tool, the session catalog
  injection and the ``/name`` user invocation.

This module implements the *same contract* inside PureGamma, because PureGamma
is a multi-tenant product: the Harness web server is a single-operator
localhost tool with no user, session or tenant model, so it cannot be the
online entry point.  What is shared with upstream is the format and the
semantics, not a process:

* discovery      - ``<root>/<name>/SKILL.md`` or ``<root>/<name>.md``, depth 2;
* frontmatter    - ``name`` (kebab-case) and ``description`` are required;
* model surface  - a session catalog rendered as ``<available_skills>``;
* user surface   - ``/name`` in the user's own message loads that skill;
* content wrapper- ``render_skill_content`` is byte-compatible with upstream.

Skills are text.  Loading one injects instructions; it never grants a tool, a
data source or a permission.  Every call still passes the existing PureGamma
entitlement, quota and billing path.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

logger = logging.getLogger(__name__)

#: Upstream requires a kebab-case name; anything else is refused.
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
#: Upstream's user-invocation gesture: whitespace-bounded ``/name``.  ``/usr/bin``
#: and ``5/8`` do not match.  Only the user's OWN message is ever scanned, so
#: retrieved content cannot forge the gesture.
INVOCATION_RE = re.compile(r"(^|\s)/([a-z0-9]+(?:-[a-z0-9]+)*)(?=\s|$)")
#: A YAML boolean, spelled the way upstream accepts it.
_TRUE = {"true", "yes", "on", "1"}
_FALSE = {"false", "no", "off", "0"}
#: Camel-case spellings are hard errors upstream, never silent aliases.
FOREIGN_BOOLEAN_KEYS = ("disableModelInvocation", "modelInvocable", "userInvocable")


class SkillFormatError(ValueError):
    """Raised for a malformed skill file; the caller drops that one skill."""


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str
    when_to_use: str | None
    body: str
    file: str
    resource_base: str
    model_invocable: bool = True
    user_invocable: bool = True
    #: Free-form frontmatter ``metadata`` (upstream allows any object).  The
    #: migrated PureGamma skills keep their original registry slug here so the
    #: existing ``skill_runs`` audit rows stay reconcilable.
    metadata: dict | None = None

    @property
    def legacy_slug(self) -> str | None:
        value = (self.metadata or {}).get("legacy_slug")
        return value if isinstance(value, str) and value else None

    def as_catalog_entry(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "whenToUse": self.when_to_use,
            "modelInvocable": self.model_invocable,
            "userInvocable": self.user_invocable,
        }


def _frontmatter_boolean(value: object, key: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
    # Upstream drops the whole skill rather than silently permitting a surface.
    raise SkillFormatError(f"frontmatter {key!r} is not a boolean: {value!r}")


def parse_skill_text(text: str, *, file: str, resource_base: str) -> SkillEntry:
    """Parse one ``SKILL.md`` exactly the way upstream does."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise SkillFormatError("frontmatter must start with '---' on the first line")
    closing = next((index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if closing is None:
        raise SkillFormatError("frontmatter is not closed by '---'")
    try:
        meta = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as exc:
        raise SkillFormatError(f"frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise SkillFormatError("frontmatter must be a YAML object")
    body = "\n".join(lines[closing + 1:]).strip()

    for foreign in FOREIGN_BOOLEAN_KEYS:
        if foreign in meta:
            raise SkillFormatError(f"{foreign!r} is not accepted; use the kebab-case key")

    name = meta.get("name")
    if not isinstance(name, str) or not SKILL_NAME_RE.match(name):
        raise SkillFormatError(f"invalid skill name {name!r}")

    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        raise SkillFormatError(f"skill {name!r} requires a non-empty description")

    when_to_use = meta.get("whenToUse")
    if when_to_use is not None and (not isinstance(when_to_use, str) or not when_to_use.strip()):
        raise SkillFormatError(f"skill {name!r} has an empty whenToUse")

    metadata = meta.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise SkillFormatError(f"skill {name!r} metadata must be an object")

    return SkillEntry(
        name=name,
        description=description.strip(),
        when_to_use=when_to_use.strip() if isinstance(when_to_use, str) else None,
        body=body.strip(),
        file=file,
        resource_base=resource_base,
        model_invocable=(
            True
            if "disable-model-invocation" not in meta
            else not _frontmatter_boolean(meta["disable-model-invocation"], "disable-model-invocation")
        ),
        user_invocable=(
            True
            if "user-invocable" not in meta
            else _frontmatter_boolean(meta["user-invocable"], "user-invocable")
        ),
        metadata=metadata if isinstance(metadata, dict) else None,
    )


def discover(root: Path) -> tuple[SkillEntry, ...]:
    """Every valid skill directly under ``root`` (depth 2, like upstream).

    A malformed file is logged and skipped; it never aborts discovery.
    """
    if not root.is_dir():
        return ()
    entries: list[SkillEntry] = []
    for child in sorted(root.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            file = child / "SKILL.md"
            resource_base = str(child)
        elif child.suffix == ".md":
            file = child
            resource_base = str(root)
        else:
            continue
        if not file.is_file():
            continue
        try:
            entries.append(
                parse_skill_text(
                    file.read_text(encoding="utf-8"),
                    file=str(file),
                    resource_base=resource_base,
                )
            )
        except (OSError, UnicodeDecodeError, SkillFormatError) as exc:
            logger.warning("skill file %s ignored: %s", file, exc)
    # Upstream sorts the catalog by code-point name order.
    entries.sort(key=lambda item: item.name)
    return tuple(entries)


def resolve(entries: Iterable[SkillEntry], name: str) -> SkillEntry | None:
    for entry in entries:
        if entry.name == name:
            return entry
    return None


def user_invocations(text: str) -> tuple[str, ...]:
    """Skill names named by ``/name`` in a user's own message, first-seen order."""
    seen: list[str] = []
    for _prefix, name in INVOCATION_RE.findall(text or ""):
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def render_catalog_message(entries: Iterable[SkillEntry]) -> str:
    """The session catalog, in upstream's model-facing shape."""
    lines = [
        "<system-reminder>",
        "The following skills are available. A user loads one by typing its name",
        "with a leading slash (for example `/market-research`); the loaded skill's",
        "instructions are appended to this conversation. Skills are reference",
        "material, never permissions.",
        "",
        "<available_skills>",
    ]
    for entry in entries:
        lines.append(f"- `{entry.name}`: {' '.join(entry.description.split())}")
    lines.extend(["</available_skills>", "</system-reminder>"])
    return "\n".join(lines)


def render_skill_content(entry: SkillEntry) -> str:
    """The canonical wrapper, shared by the tool result and the ``/name`` path."""
    return (
        f'<skill_content name="{entry.name}">\n'
        f"<skill_resources>{entry.file}</skill_resources>\n\n"
        f"<skill_instructions>\n{entry.body}\n</skill_instructions>\n"
        f"</skill_content>"
    )


def model_catalog(entries: Iterable[SkillEntry]) -> tuple[SkillEntry, ...]:
    return tuple(entry for entry in entries if entry.model_invocable)


def load_user_skills(entries: Iterable[SkillEntry], text: str) -> tuple[SkillEntry, ...]:
    """Resolve the ``/name`` gestures in a user's own message.

    An unknown name, or one that is not user-invocable, stays plain prose
    (upstream behaves the same way).
    """
    loaded: list[SkillEntry] = []
    for name in user_invocations(text):
        entry = resolve(entries, name)
        if entry is None:
            logger.info("skill %r named by the user is unknown", name)
            continue
        if not entry.user_invocable:
            logger.info("skill %r is not user-invocable", name)
            continue
        loaded.append(entry)
    return tuple(loaded)


# --------------------------------------------------------------------- catalog

#: The packaged PureGamma skills ship with the image; a deployment may add its
#: own directory through ``AGENT_SKILLS_DIR`` without rebuilding.
DEFAULT_SKILLS_DIRNAME = "skills"
_catalog_cache: tuple[str, float, tuple[SkillEntry, ...]] | None = None


def default_skills_dir() -> Path:
    """``apps/api/skills`` next to this file, independent of the process CWD."""
    return Path(__file__).resolve().parent.parent / DEFAULT_SKILLS_DIRNAME


def catalog_root() -> Path:
    from apps.api.config import get_settings

    configured = (get_settings().agent_skills_dir or "").strip()
    return Path(configured) if configured else default_skills_dir()


def catalog() -> tuple[SkillEntry, ...]:
    """The deployment's skill catalog, re-read when the directory changes.

    A missing or unreadable directory yields an empty catalog, never an error:
    an agent with no skills still answers, it simply has nothing to load.
    """
    global _catalog_cache
    root = catalog_root()
    try:
        stamp = root.stat().st_mtime
    except OSError:
        stamp = -1.0
    key = str(root)
    if _catalog_cache is not None and _catalog_cache[0] == key and _catalog_cache[1] == stamp:
        return _catalog_cache[2]
    entries = discover(root)
    _catalog_cache = (key, stamp, entries)
    return entries


def reset_catalog_cache() -> None:
    """Drop the cached catalog (tests, or a deployment that rewrote the dir)."""
    global _catalog_cache
    _catalog_cache = None


def skill_prompt(catalog_entries: Iterable[SkillEntry], loaded: Iterable[SkillEntry]) -> str:
    """What the model receives: the catalog, then any skill the user loaded.

    Matches upstream ordering: the ``/name`` content is injected after the
    catalog, and both are reference material - never permissions.
    """
    parts: list[str] = []
    catalog_text = render_catalog_message(catalog_entries)
    if catalog_text:
        parts.append(catalog_text)
    for entry in loaded:
        parts.append(render_skill_content(entry))
    return "\n\n".join(parts)


def agent_skill_catalog() -> list[dict]:
    """The user-invocable catalog the client offers as `/` suggestions.

    Mirrors upstream's ``skills/list``: every user-invocable skill, including a
    model-disabled one, whose only entry point is the user's own message.
    """
    return [entry.as_catalog_entry() for entry in catalog() if entry.user_invocable]


def resolve_loaded(context: dict, entries: Iterable[SkillEntry]) -> tuple[SkillEntry, ...]:
    """Re-resolve, at run time, the skills the request recorded as loaded.

    The stored run context carries skill *names* (``agent_skills.loaded``), so
    streaming a run started moments ago loads the same instructions, and a skill
    that has since been removed simply does not load - the run is never blocked
    by a missing instruction file.
    """
    names = (context.get("agent_skills") or {}).get("loaded") or []
    resolved: list[SkillEntry] = []
    for name in names:
        entry = resolve(entries, str(name))
        if entry is not None:
            resolved.append(entry)
        else:
            logger.warning("skill %r recorded on this run is no longer installed", name)
    return tuple(resolved)
