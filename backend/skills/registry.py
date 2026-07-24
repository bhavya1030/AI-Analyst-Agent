"""SkillRegistry — planner-facing catalog of discovered analytical skills."""

from __future__ import annotations

import threading
from typing import Any, Iterable, Optional, Sequence

from backend.core.logger import get_logger
from backend.skills.base import Skill, is_valid_skill, validate_skill_interface
from backend.skills.metadata import SkillMetadata, SkillRegistration

logger = get_logger(__name__)


class SkillRegistryError(Exception):
    """Registry operation failed."""


class SkillRegistry:
    """
    Thread-safe registry of analytical skills.

    Planner later uses this registry without code changes to skill plugins.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._skills: dict[str, SkillRegistration] = {}
        self._rejected: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        skill: Skill | Any,
        *,
        metadata: SkillMetadata | None = None,
        replace: bool = True,
        validate: bool = True,
    ) -> SkillRegistration:
        """
        Register a skill instance.

        Invalid skills are rejected (not registered) when validate=True.
        """
        if skill is None:
            raise SkillRegistryError("skill is required")

        # Instantiate class if a Skill subclass / type is passed
        instance = skill
        if isinstance(skill, type):
            try:
                instance = skill()  # type: ignore[call-arg]
            except Exception as exc:
                # Abstract / broken constructors → reject rather than raise
                meta = metadata or SkillMetadata(
                    skill_id=_slug(getattr(skill, "name", None) or skill.__name__),
                    name=str(getattr(skill, "name", None) or skill.__name__),
                    description=str(getattr(skill, "description", None) or ""),
                    class_name=skill.__name__,
                    module=str(getattr(skill, "__module__", "") or ""),
                )
                reason = f"Cannot instantiate skill class: {exc}"
                reg = SkillRegistration(
                    skill=skill,
                    metadata=meta,
                    valid=False,
                    rejection_reason=reason,
                )
                with self._lock:
                    self._rejected.append(reg.to_dict())
                logger.warning(
                    "Rejected invalid skill plugin",
                    extra={"skill_id": meta.skill_id, "reason": reason},
                )
                return reg

        errors = validate_skill_interface(instance) if validate else []
        meta = metadata or _metadata_from_skill(instance)

        if errors:
            reason = "; ".join(errors)
            reg = SkillRegistration(
                skill=instance,
                metadata=meta,
                valid=False,
                rejection_reason=reason,
            )
            with self._lock:
                self._rejected.append(reg.to_dict())
            logger.warning(
                "Rejected invalid skill plugin",
                extra={"skill_id": meta.skill_id, "reason": reason},
            )
            return reg

        if not meta.skill_id:
            meta.skill_id = _slug(meta.name or type(instance).__name__)

        with self._lock:
            if meta.skill_id in self._skills and not replace:
                raise SkillRegistryError(f"Skill already registered: {meta.skill_id}")
            # Dependency check against currently registered
            available = set(self._skills.keys()) | {meta.skill_id}
            ok, missing = meta.satisfies_dependencies(available)
            if not ok:
                # Allow register but mark warning in extra; hard-reject only if strict deps missing
                # and dependency is required for enablement — keep soft: store with enabled note
                meta.extra = dict(meta.extra or {})
                meta.extra["missing_dependencies"] = missing
                logger.warning(
                    "Skill has unresolved dependencies",
                    extra={"skill_id": meta.skill_id, "missing": missing},
                )

            reg = SkillRegistration(skill=instance, metadata=meta, valid=True)
            self._skills[meta.skill_id] = reg
            logger.info(
                "Skill registered",
                extra={"skill_id": meta.skill_id, "version": meta.version},
            )
            return reg

    def unregister(self, skill_id: str) -> bool:
        with self._lock:
            return self._skills.pop((skill_id or "").strip(), None) is not None

    def clear(self) -> None:
        with self._lock:
            self._skills.clear()
            self._rejected.clear()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, skill_id: str) -> Optional[SkillRegistration]:
        with self._lock:
            return self._skills.get((skill_id or "").strip())

    def get_skill(self, skill_id: str) -> Optional[Any]:
        reg = self.get(skill_id)
        return reg.skill if reg else None

    def list_ids(self, *, enabled_only: bool = True) -> list[str]:
        with self._lock:
            items = list(self._skills.values())
        if enabled_only:
            items = [r for r in items if r.metadata.enabled]
        return sorted(r.metadata.skill_id for r in items)

    def list_skills(self, *, enabled_only: bool = True) -> list[SkillRegistration]:
        with self._lock:
            items = list(self._skills.values())
        if enabled_only:
            items = [r for r in items if r.metadata.enabled]
        return sorted(items, key=lambda r: r.metadata.skill_id)

    def list_metadata(self, *, enabled_only: bool = True) -> list[SkillMetadata]:
        return [r.metadata for r in self.list_skills(enabled_only=enabled_only)]

    def rejected(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._rejected)

    def record_rejection(
        self,
        *,
        skill_id: str = "",
        name: str = "",
        reason: str,
        metadata: SkillMetadata | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Record a rejected plugin without registering it."""
        payload = {
            "skill_id": skill_id or (metadata.skill_id if metadata else ""),
            "name": name or (metadata.name if metadata else ""),
            "reason": reason,
            "metadata": metadata.to_dict() if metadata else {},
            "extra": dict(extra or {}),
        }
        with self._lock:
            self._rejected.append(payload)
        logger.warning(
            "Rejected invalid skill plugin",
            extra={"skill_id": payload["skill_id"], "reason": reason},
        )

    def match_question(self, question: str) -> list[SkillRegistration]:
        """Return skills whose supported_questions match the user question."""
        hits = []
        for reg in self.list_skills(enabled_only=True):
            skill = reg.skill
            if hasattr(skill, "matches_question") and skill.matches_question(question):
                hits.append(reg)
            else:
                # fallback keyword check on metadata
                q = (question or "").lower()
                if any((p or "").lower() in q for p in reg.metadata.supported_questions):
                    hits.append(reg)
        return hits

    def match_dataset_type(self, dataset_type: str) -> list[SkillRegistration]:
        hits = []
        for reg in self.list_skills(enabled_only=True):
            skill = reg.skill
            if hasattr(skill, "supports_dataset_type"):
                if skill.supports_dataset_type(dataset_type):
                    hits.append(reg)
            else:
                types = [t.lower() for t in reg.metadata.supported_dataset_types]
                if not types or "*" in types or (dataset_type or "").lower() in types:
                    hits.append(reg)
        return hits

    def __len__(self) -> int:
        with self._lock:
            return len(self._skills)

    def __contains__(self, skill_id: str) -> bool:
        with self._lock:
            return (skill_id or "").strip() in self._skills

    def to_dict(self) -> dict[str, Any]:
        return {
            "skills": [r.to_dict() for r in self.list_skills(enabled_only=False)],
            "rejected": self.rejected(),
            "n_skills": len(self),
        }


def _metadata_from_skill(skill: Any) -> SkillMetadata:
    if hasattr(skill, "metadata") and callable(skill.metadata):
        try:
            meta = skill.metadata()
            if isinstance(meta, SkillMetadata):
                return meta
            if isinstance(meta, dict):
                return SkillMetadata.from_dict(meta)
        except Exception:
            pass
    return SkillMetadata(
        skill_id=_slug(getattr(skill, "name", None) or type(skill).__name__),
        name=str(getattr(skill, "name", None) or type(skill).__name__),
        description=str(getattr(skill, "description", None) or ""),
        version=str(getattr(skill, "version", "1.0.0")),
        dependencies=list(getattr(skill, "dependencies", []) or []),
        supported_dataset_types=list(getattr(skill, "supported_dataset_types", []) or []),
        supported_questions=list(getattr(skill, "supported_questions", []) or []),
        module=str(getattr(skill, "__module__", "") or ""),
        class_name=type(skill).__name__,
    )


def _slug(text: str) -> str:
    import re

    s = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower())
    return s.strip("_") or "skill"


# Process-wide default registry (Planner later binds to this)
_default_registry: SkillRegistry | None = None
_reg_lock = threading.Lock()


def get_skill_registry() -> SkillRegistry:
    global _default_registry
    with _reg_lock:
        if _default_registry is None:
            _default_registry = SkillRegistry()
        return _default_registry


def set_skill_registry(registry: SkillRegistry) -> None:
    global _default_registry
    with _reg_lock:
        _default_registry = registry


def reset_skill_registry() -> None:
    global _default_registry
    with _reg_lock:
        if _default_registry is not None:
            _default_registry.clear()
        _default_registry = None
