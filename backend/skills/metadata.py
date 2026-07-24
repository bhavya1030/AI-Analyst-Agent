"""Plugin metadata for analytical skills."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SkillMetadata:
    """
    Declarative metadata attached to a registered skill.

    Supports versioning and dependency declarations for future planners.
    """

    skill_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    dependencies: list[str] = field(default_factory=list)
    supported_dataset_types: list[str] = field(default_factory=list)
    supported_questions: list[str] = field(default_factory=list)
    author: str = ""
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    module: str = ""
    class_name: str = ""
    entry_path: str = ""  # filesystem path if loaded from file
    discovered_at: str = field(default_factory=_utc_now_iso)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SkillMetadata":
        data = data or {}
        return cls(
            skill_id=str(data.get("skill_id") or data.get("id") or "").strip(),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            version=str(data.get("version") or "1.0.0"),
            dependencies=[str(d) for d in (data.get("dependencies") or [])],
            supported_dataset_types=[
                str(t) for t in (data.get("supported_dataset_types") or [])
            ],
            supported_questions=[
                str(q) for q in (data.get("supported_questions") or [])
            ],
            author=str(data.get("author") or ""),
            tags=[str(t) for t in (data.get("tags") or [])],
            enabled=bool(data.get("enabled", True)),
            module=str(data.get("module") or ""),
            class_name=str(data.get("class_name") or ""),
            entry_path=str(data.get("entry_path") or data.get("path") or ""),
            discovered_at=str(data.get("discovered_at") or _utc_now_iso()),
            extra=dict(data.get("extra") or data.get("metadata") or {}),
        )

    def satisfies_dependencies(self, available_ids: set[str]) -> tuple[bool, list[str]]:
        """Return (ok, missing_dependency_ids)."""
        missing = [d for d in self.dependencies if d and d not in available_ids]
        return (len(missing) == 0, missing)


@dataclass
class SkillRegistration:
    """A skill instance bound to its metadata inside the registry."""

    skill: Any
    metadata: SkillMetadata
    valid: bool = True
    rejection_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "valid": self.valid,
            "rejection_reason": self.rejection_reason,
            "skill_class": type(self.skill).__name__,
        }
