"""Analytical Skills — plugin interface, registry, and automatic discovery.

Planner later uses SkillRegistry without changing skill plugin code.
"""

from backend.skills.base import Skill, SkillValidationError, is_valid_skill, validate_skill_interface
from backend.skills.discovery import (
    DiscoveryReport,
    SkillDiscovery,
    discover_skills,
    get_skill_discovery,
    hot_reload_skills,
    reset_skill_discovery,
)
from backend.skills.loader import SkillLoadError, SkillLoader
from backend.skills.metadata import SkillMetadata, SkillRegistration
from backend.skills.registry import (
    SkillRegistry,
    SkillRegistryError,
    get_skill_registry,
    reset_skill_registry,
    set_skill_registry,
)

__all__ = [
    # Base
    "Skill",
    "SkillValidationError",
    "validate_skill_interface",
    "is_valid_skill",
    # Metadata
    "SkillMetadata",
    "SkillRegistration",
    # Registry
    "SkillRegistry",
    "SkillRegistryError",
    "get_skill_registry",
    "set_skill_registry",
    "reset_skill_registry",
    # Loader / discovery
    "SkillLoader",
    "SkillLoadError",
    "SkillDiscovery",
    "DiscoveryReport",
    "discover_skills",
    "hot_reload_skills",
    "get_skill_discovery",
    "reset_skill_discovery",
]
