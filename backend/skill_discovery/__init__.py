"""Automatic Skill Discovery — find and register analytical tools.

Discovers skills from decorators, agent modules, manifests, and entry points,
then registers them into the existing ToolRegistry without redesigning
tool selection.
"""

from backend.skill_discovery.decorators import (
    analytical_skill,
    clear_declared_skills,
    get_declared_skills,
    skill,
)
from backend.skill_discovery.discovery import (
    SkillDiscoveryService,
    auto_discover_and_register,
    discover_skills,
    get_discovery_service,
    register_discovered_skills,
    reset_discovery_service,
)
from backend.skill_discovery.models import DiscoveredSkill, DiscoveryResult, SkillSource
from backend.skill_discovery.scanner import SkillScanner

__all__ = [
    # API
    "discover_skills",
    "register_discovered_skills",
    "auto_discover_and_register",
    "SkillDiscoveryService",
    "get_discovery_service",
    "reset_discovery_service",
    # Decorator
    "analytical_skill",
    "skill",
    "get_declared_skills",
    "clear_declared_skills",
    # Models / scanner
    "DiscoveredSkill",
    "DiscoveryResult",
    "SkillSource",
    "SkillScanner",
]
