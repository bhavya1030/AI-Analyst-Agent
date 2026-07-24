"""Models for Automatic Skill Discovery."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SkillSource(str, Enum):
    """Where a skill was discovered."""

    DECORATOR = "decorator"
    AGENT_MODULE = "agent_module"
    MANIFEST = "manifest"
    ENTRY_POINT = "entry_point"
    BUILTIN_CATALOG = "builtin_catalog"
    CUSTOM_PATH = "custom_path"


@dataclass
class DiscoveredSkill:
    """
    A discovered analytical skill / tool candidate.

    Convertible to tool_selection.ToolSpec for registration.
    """

    skill_id: str
    name: str
    description: str = ""
    category: str = "general"
    keywords: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    produces_chart: bool = False
    priority: int = 100
    enabled: bool = True
    version: str = "1.0"
    source: SkillSource = SkillSource.CUSTOM_PATH
    module: str = ""
    callable_name: str = ""
    entry_point: str = ""
    manifest_path: str = ""
    # Optional callable reference (not serialized for persistence)
    handler: Optional[Callable[..., Any]] = field(default=None, repr=False)
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "keywords": list(self.keywords),
            "intents": list(self.intents),
            "tags": list(self.tags),
            "produces_chart": self.produces_chart,
            "priority": self.priority,
            "enabled": self.enabled,
            "version": self.version,
            "source": self.source.value
            if isinstance(self.source, SkillSource)
            else self.source,
            "module": self.module,
            "callable_name": self.callable_name,
            "entry_point": self.entry_point,
            "manifest_path": self.manifest_path,
            "metadata": dict(self.metadata),
            "discovered_at": self.discovered_at,
            "has_handler": self.handler is not None,
        }

    def to_tool_spec_dict(self) -> dict[str, Any]:
        """Payload accepted by ToolRegistry.register_spec."""
        return {
            "tool_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "keywords": list(self.keywords),
            "intents": list(self.intents),
            "tags": list(self.tags) + ["discovered", self.source.value if isinstance(self.source, SkillSource) else str(self.source)],
            "produces_chart": self.produces_chart,
            "priority": self.priority,
            "enabled": self.enabled,
            "is_plugin": self.source
            not in {SkillSource.BUILTIN_CATALOG},
            "version": self.version,
            "metadata": {
                **dict(self.metadata),
                "discovered": True,
                "source": self.source.value
                if isinstance(self.source, SkillSource)
                else self.source,
                "module": self.module,
                "callable_name": self.callable_name,
                "entry_point": self.entry_point,
                "manifest_path": self.manifest_path,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DiscoveredSkill":
        data = data or {}
        src = data.get("source") or SkillSource.CUSTOM_PATH
        if isinstance(src, str):
            try:
                src = SkillSource(src)
            except ValueError:
                src = SkillSource.CUSTOM_PATH
        return cls(
            skill_id=str(data.get("skill_id") or data.get("tool_id") or data.get("id") or "").strip(),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            category=str(data.get("category") or "general"),
            keywords=[str(k) for k in (data.get("keywords") or [])],
            intents=[str(i) for i in (data.get("intents") or [])],
            tags=[str(t) for t in (data.get("tags") or [])],
            produces_chart=bool(data.get("produces_chart", False)),
            priority=int(data.get("priority") or 100),
            enabled=bool(data.get("enabled", True)),
            version=str(data.get("version") or "1.0"),
            source=src,
            module=str(data.get("module") or ""),
            callable_name=str(data.get("callable_name") or ""),
            entry_point=str(data.get("entry_point") or ""),
            manifest_path=str(data.get("manifest_path") or ""),
            metadata=dict(data.get("metadata") or {}),
            discovered_at=str(data.get("discovered_at") or _utc_now_iso()),
        )


@dataclass
class DiscoveryResult:
    """Outcome of a discovery run."""

    skills: list[DiscoveredSkill] = field(default_factory=list)
    registered_ids: list[str] = field(default_factory=list)
    skipped_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    sources_scanned: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    registered: bool = False

    @property
    def skill_ids(self) -> list[str]:
        return [s.skill_id for s in self.skills]

    def to_dict(self) -> dict[str, Any]:
        return {
            "skills": [s.to_dict() for s in self.skills],
            "skill_ids": self.skill_ids,
            "registered_ids": list(self.registered_ids),
            "skipped_ids": list(self.skipped_ids),
            "errors": list(self.errors),
            "sources_scanned": list(self.sources_scanned),
            "duration_seconds": self.duration_seconds,
            "registered": self.registered,
            "n_skills": len(self.skills),
            "n_registered": len(self.registered_ids),
        }
