"""Base interface for analytical skills / plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, Sequence

from backend.skills.metadata import SkillMetadata


class SkillValidationError(Exception):
    """Skill does not satisfy the required interface."""


class Skill(ABC):
    """
    Analytical skill contract.

    Required surface:
      - name
      - description
      - execute()
      - supported_dataset_types
      - supported_questions
    """

    # Optional class-level defaults (subclasses may override as attributes)
    name: str = ""
    description: str = ""
    supported_dataset_types: Sequence[str] = ()
    supported_questions: Sequence[str] = ()

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Run the skill. Implementation-defined I/O."""

    def metadata(self) -> SkillMetadata:
        """
        Plugin metadata (version, dependencies, etc.).

        Override for richer plugins; default derives from class attributes.
        """
        return SkillMetadata(
            skill_id=getattr(self, "skill_id", None) or _slug(self.name or type(self).__name__),
            name=self.name or type(self).__name__,
            description=self.description or (type(self).__doc__ or "").strip().split("\n")[0],
            version=str(getattr(self, "version", "1.0.0")),
            dependencies=list(getattr(self, "dependencies", []) or []),
            supported_dataset_types=list(self.supported_dataset_types or []),
            supported_questions=list(self.supported_questions or []),
            author=str(getattr(self, "author", "") or ""),
            tags=list(getattr(self, "tags", []) or []),
            enabled=bool(getattr(self, "enabled", True)),
            module=str(getattr(self, "__module__", "") or ""),
            class_name=type(self).__name__,
        )

    def supports_dataset_type(self, dataset_type: str) -> bool:
        types = [t.lower() for t in (self.supported_dataset_types or [])]
        if not types or "*" in types or "any" in types:
            return True
        return (dataset_type or "").lower() in types

    def matches_question(self, question: str) -> bool:
        """True if any supported_questions keyword/phrase appears in question."""
        q = (question or "").lower()
        if not self.supported_questions:
            return False
        for pattern in self.supported_questions:
            p = (pattern or "").lower().strip()
            if p and p in q:
                return True
        return False


def validate_skill_interface(obj: Any) -> list[str]:
    """
    Validate that obj implements the Skill interface.

    Returns a list of error strings (empty if valid).
    """
    errors: list[str] = []
    if obj is None:
        return ["skill is None"]

    # Must be Skill subclass instance or class
    is_class = isinstance(obj, type)
    candidate = obj if not is_class else obj

    if is_class:
        if not issubclass(obj, Skill):
            # Duck-typing for plain classes
            pass
        instance_probe = None
        try:
            # Prefer not to instantiate arbitrary classes with required args;
            # validate on class attributes + execute presence.
            instance_probe = None
        except Exception:
            instance_probe = None
        target = obj
    else:
        target = obj

    # name
    name = getattr(target, "name", None)
    if callable(name) and not isinstance(name, type):
        try:
            name = name()
        except TypeError:
            pass
    if not name or not str(name).strip():
        # allow class name fallback only for instances that set it later
        if not (is_class and getattr(target, "__name__", None)):
            errors.append("missing non-empty 'name'")

    # description
    desc = getattr(target, "description", None)
    if desc is None:
        errors.append("missing 'description'")

    # execute
    execute = getattr(target, "execute", None)
    if execute is None or not callable(execute):
        errors.append("missing callable execute()")
    elif is_class and getattr(execute, "__isabstractmethod__", False):
        errors.append("execute() is abstract (not implemented)")

    # supported_dataset_types
    if not hasattr(target, "supported_dataset_types"):
        errors.append("missing supported_dataset_types")
    else:
        sdt = getattr(target, "supported_dataset_types")
        if callable(sdt) and not isinstance(sdt, type):
            try:
                sdt = sdt()
            except TypeError:
                pass
        if sdt is None or not isinstance(sdt, (list, tuple, set)):
            errors.append("supported_dataset_types must be a sequence")

    # supported_questions
    if not hasattr(target, "supported_questions"):
        errors.append("missing supported_questions")
    else:
        sq = getattr(target, "supported_questions")
        if callable(sq) and not isinstance(sq, type):
            try:
                sq = sq()
            except TypeError:
                pass
        if sq is None or not isinstance(sq, (list, tuple, set)):
            errors.append("supported_questions must be a sequence")

    # If class subclassing Skill, try lightweight instantiation for abstract check
    if is_class and isinstance(obj, type) and issubclass(obj, Skill):
        try:
            # only zero-arg constructors
            inst = obj()  # type: ignore[call-arg]
            if getattr(type(inst).execute, "__isabstractmethod__", False):
                errors.append("execute() is abstract (not implemented)")
        except TypeError:
            # constructor requires args — duck interface already checked
            pass
        except Exception as exc:
            errors.append(f"cannot instantiate skill: {exc}")

    return errors


def is_valid_skill(obj: Any) -> bool:
    return len(validate_skill_interface(obj)) == 0


def _slug(text: str) -> str:
    import re

    s = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower())
    return s.strip("_") or "skill"
