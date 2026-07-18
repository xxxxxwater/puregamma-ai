"""Versioned, declarative PureGamma Skills infrastructure."""

from packages.skills.manifest import SkillManifest, validate_skill_bundle
from packages.skills.registry import SkillActor, SkillRegistry, SkillResolutionError

__all__ = [
    "SkillActor",
    "SkillManifest",
    "SkillRegistry",
    "SkillResolutionError",
    "validate_skill_bundle",
]
