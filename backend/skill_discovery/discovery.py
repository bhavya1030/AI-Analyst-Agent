"""Automatic Skill Discovery orchestrator.

Discovers analytical skills and registers them into the tool registry
without redesigning tool_selection.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from backend.core.logger import get_logger
from backend.skill_discovery.models import DiscoveredSkill, DiscoveryResult, SkillSource
from backend.skill_discovery.scanner import SkillScanner

logger = get_logger(__name__)


class SkillDiscoveryService:
    """
    Discover and optionally auto-register analytical skills/tools.

    Sources:
      1. @analytical_skill decorators
      2. backend.agents modules (convention map)
      3. skill_manifest.json files
      4. package entry points (analytics_copilot.skills)
      5. module attribute exports (SKILLS / TOOLS)
    """

    def __init__(self, scanner: SkillScanner | None = None):
        self._scanner = scanner or SkillScanner()

    def discover(
        self,
        *,
        include_decorators: bool = True,
        include_agents: bool = True,
        agent_package: str = "backend.agents",
        manifest_paths: Sequence[str | Path] | None = None,
        include_entry_points: bool = True,
        entry_point_group: str = "analytics_copilot.skills",
        extra_modules: Sequence[str] | None = None,
        dedupe: bool = True,
    ) -> DiscoveryResult:
        """Scan configured sources and return discovered skills (no registration)."""
        t0 = time.perf_counter()
        result = DiscoveryResult()
        found: list[DiscoveredSkill] = []

        if include_decorators:
            result.sources_scanned.append("decorators")
            try:
                found.extend(self._scanner.scan_decorators())
            except Exception as exc:
                result.errors.append(f"decorators: {exc}")

        if include_agents:
            result.sources_scanned.append(f"agents:{agent_package}")
            try:
                found.extend(self._scanner.scan_agent_package(agent_package))
            except Exception as exc:
                result.errors.append(f"agents: {exc}")

        if manifest_paths:
            result.sources_scanned.append("manifests")
            try:
                found.extend(self._scanner.scan_manifests(manifest_paths))
            except Exception as exc:
                result.errors.append(f"manifests: {exc}")

        if include_entry_points:
            result.sources_scanned.append(f"entry_points:{entry_point_group}")
            try:
                found.extend(self._scanner.scan_entry_points(entry_point_group))
            except Exception as exc:
                result.errors.append(f"entry_points: {exc}")

        for mod in extra_modules or []:
            result.sources_scanned.append(f"module:{mod}")
            try:
                found.extend(self._scanner.scan_module_attributes(mod))
            except Exception as exc:
                result.errors.append(f"module:{mod}: {exc}")

        if dedupe:
            found = _dedupe_skills(found)

        result.skills = found
        result.duration_seconds = round(time.perf_counter() - t0, 4)
        logger.info(
            "Skill discovery complete",
            extra={
                "n_skills": len(found),
                "sources": result.sources_scanned,
                "seconds": result.duration_seconds,
            },
        )
        return result

    def register(
        self,
        skills: Sequence[DiscoveredSkill],
        *,
        registry: Any = None,
        replace: bool = True,
        skip_existing: bool = False,
    ) -> DiscoveryResult:
        """
        Register discovered skills into a ToolRegistry.

        Uses public ToolRegistry.register_spec API — does not redesign selection.
        """
        from backend.tool_selection.registry import (
            ToolRegistry,
            get_default_registry,
        )

        # NOTE: empty ToolRegistry is falsy (defines __len__), so never use `registry or ...`
        reg: ToolRegistry = registry if registry is not None else get_default_registry()
        result = DiscoveryResult(skills=list(skills), registered=True)
        t0 = time.perf_counter()

        for skill in skills:
            if not skill.skill_id or not skill.enabled:
                result.skipped_ids.append(skill.skill_id or "?")
                continue
            if skip_existing and skill.skill_id in reg:
                result.skipped_ids.append(skill.skill_id)
                continue
            try:
                reg.register_spec(skill.to_tool_spec_dict(), replace=replace)
                result.registered_ids.append(skill.skill_id)
            except Exception as exc:
                result.errors.append(f"register {skill.skill_id}: {exc}")
                result.skipped_ids.append(skill.skill_id)

        result.duration_seconds = round(time.perf_counter() - t0, 4)
        logger.info(
            "Skills registered",
            extra={
                "n_registered": len(result.registered_ids),
                "n_skipped": len(result.skipped_ids),
                "n_errors": len(result.errors),
            },
        )
        return result

    def discover_and_register(self, **kwargs: Any) -> DiscoveryResult:
        """
        Full pipeline: discover → register into default (or provided) registry.

        Extra kwargs:
          registry, replace, skip_existing, plus discover() options.
        """
        registry = kwargs.pop("registry", None)
        replace = kwargs.pop("replace", True)
        skip_existing = kwargs.pop("skip_existing", False)

        discovered = self.discover(**kwargs)
        reg_result = self.register(
            discovered.skills,
            registry=registry,
            replace=replace,
            skip_existing=skip_existing,
        )
        discovered.registered_ids = reg_result.registered_ids
        discovered.skipped_ids = reg_result.skipped_ids
        discovered.errors.extend(reg_result.errors)
        discovered.registered = True
        discovered.duration_seconds = round(
            discovered.duration_seconds + reg_result.duration_seconds, 4
        )
        return discovered


def _dedupe_skills(skills: list[DiscoveredSkill]) -> list[DiscoveredSkill]:
    """Prefer decorator > manifest > entry_point > agent > other for same skill_id."""
    priority = {
        SkillSource.DECORATOR: 0,
        SkillSource.MANIFEST: 1,
        SkillSource.ENTRY_POINT: 2,
        SkillSource.AGENT_MODULE: 3,
        SkillSource.BUILTIN_CATALOG: 4,
        SkillSource.CUSTOM_PATH: 5,
    }
    best: dict[str, DiscoveredSkill] = {}
    for s in skills:
        sid = (s.skill_id or "").strip()
        if not sid:
            continue
        prev = best.get(sid)
        if prev is None:
            best[sid] = s
            continue
        p_new = priority.get(s.source, 9)
        p_old = priority.get(prev.source, 9)
        if p_new < p_old:
            best[sid] = s
    return list(best.values())


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

_default_service: SkillDiscoveryService | None = None


def get_discovery_service() -> SkillDiscoveryService:
    global _default_service
    if _default_service is None:
        _default_service = SkillDiscoveryService()
    return _default_service


def reset_discovery_service() -> None:
    global _default_service
    _default_service = None


def discover_skills(**kwargs: Any) -> DiscoveryResult:
    """Discover skills without registration."""
    return get_discovery_service().discover(**kwargs)


def register_discovered_skills(
    skills: Sequence[DiscoveredSkill],
    **kwargs: Any,
) -> DiscoveryResult:
    """Register a list of discovered skills."""
    return get_discovery_service().register(skills, **kwargs)


def auto_discover_and_register(**kwargs: Any) -> DiscoveryResult:
    """Discover + register analytical skills automatically."""
    return get_discovery_service().discover_and_register(**kwargs)
