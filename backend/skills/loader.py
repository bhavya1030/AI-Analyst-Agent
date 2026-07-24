"""Load skill plugins from Python modules / files."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Optional

from backend.core.logger import get_logger
from backend.skills.base import Skill, is_valid_skill, validate_skill_interface
from backend.skills.metadata import SkillMetadata

logger = get_logger(__name__)

# Modules that are infrastructure, not plugins
_SKIP_MODULE_NAMES = frozenset(
    {
        "base",
        "metadata",
        "registry",
        "loader",
        "discovery",
        "__init__",
    }
)


class SkillLoadError(Exception):
    """Failed to load a skill module."""


class SkillLoader:
    """Import modules and extract Skill implementations."""

    def load_module(self, module_name: str) -> ModuleType:
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            raise SkillLoadError(f"Cannot import {module_name}: {exc}") from exc

    def load_module_from_path(
        self,
        path: str | Path,
        *,
        module_name: str | None = None,
    ) -> ModuleType:
        path = Path(path)
        if not path.is_file():
            raise SkillLoadError(f"Not a file: {path}")
        name = module_name or f"skills_plugin_{path.stem}_{abs(hash(str(path.resolve()))) & 0xFFFF}"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise SkillLoadError(f"Cannot create module spec for {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(name, None)
            raise SkillLoadError(f"Failed executing {path}: {exc}") from exc
        return module

    def reload_module(self, module_name: str) -> ModuleType:
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return self.load_module(module_name)

    def extract_skills(
        self,
        module: ModuleType,
        *,
        entry_path: str = "",
    ) -> list[tuple[Any, SkillMetadata | None, list[str]]]:
        """
        Extract skill candidates from a module.

        Returns list of (instance_or_class, optional_metadata, validation_errors).
        """
        found: list[tuple[Any, SkillMetadata | None, list[str]]] = []

        # 1) Explicit exports
        for attr in ("SKILL", "SKILLS", "PLUGIN", "PLUGINS"):
            if not hasattr(module, attr):
                continue
            raw = getattr(module, attr)
            items = raw if isinstance(raw, (list, tuple)) else [raw]
            for item in items:
                found.extend(self._coerce_item(item, entry_path=entry_path, module=module))

        # 2) Skill subclasses defined in module
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj is Skill:
                continue
            if getattr(obj, "__module__", None) != getattr(module, "__name__", None):
                continue
            try:
                if issubclass(obj, Skill):
                    found.extend(self._coerce_item(obj, entry_path=entry_path, module=module))
            except TypeError:
                continue

        # Dedupe by class/instance id
        deduped: list[tuple[Any, SkillMetadata | None, list[str]]] = []
        seen: set[int] = set()
        for item, meta, errs in found:
            key = id(item) if not isinstance(item, type) else id(item)
            # also key by skill_id if meta
            sid = meta.skill_id if meta else getattr(item, "name", None)
            sid_key = f"sid:{sid}" if sid else None
            if key in seen:
                continue
            seen.add(key)
            deduped.append((item, meta, errs))
        return deduped

    def _coerce_item(
        self,
        item: Any,
        *,
        entry_path: str,
        module: ModuleType,
    ) -> list[tuple[Any, SkillMetadata | None, list[str]]]:
        out: list[tuple[Any, SkillMetadata | None, list[str]]] = []
        if item is None:
            return out

        # Already an instance
        if not isinstance(item, type):
            errs = validate_skill_interface(item)
            meta = None
            if hasattr(item, "metadata") and callable(item.metadata):
                try:
                    m = item.metadata()
                    meta = m if isinstance(m, SkillMetadata) else SkillMetadata.from_dict(m)
                except Exception:
                    meta = None
            if meta is None:
                meta = SkillMetadata(
                    skill_id=_slug(getattr(item, "name", "") or type(item).__name__),
                    name=str(getattr(item, "name", "") or type(item).__name__),
                    description=str(getattr(item, "description", "") or ""),
                    version=str(getattr(item, "version", "1.0.0")),
                    dependencies=list(getattr(item, "dependencies", []) or []),
                    supported_dataset_types=list(
                        getattr(item, "supported_dataset_types", []) or []
                    ),
                    supported_questions=list(getattr(item, "supported_questions", []) or []),
                    module=getattr(module, "__name__", ""),
                    class_name=type(item).__name__,
                    entry_path=entry_path,
                )
            else:
                meta.module = meta.module or getattr(module, "__name__", "")
                meta.entry_path = meta.entry_path or entry_path
            out.append((item, meta, errs))
            return out

        # Class
        errs = validate_skill_interface(item)
        instance: Any = item
        if not errs:
            try:
                instance = item()  # type: ignore[call-arg]
                errs = validate_skill_interface(instance)
            except Exception as exc:
                errs = [f"cannot instantiate: {exc}"]
                instance = item
        meta = SkillMetadata(
            skill_id=_slug(
                getattr(instance, "name", None)
                or getattr(item, "name", None)
                or item.__name__
            ),
            name=str(
                getattr(instance, "name", None)
                or getattr(item, "name", None)
                or item.__name__
            ),
            description=str(
                getattr(instance, "description", None)
                or getattr(item, "description", None)
                or (item.__doc__ or "")
            ).split("\n")[0],
            version=str(
                getattr(instance, "version", None)
                or getattr(item, "version", None)
                or "1.0.0"
            ),
            dependencies=list(
                getattr(instance, "dependencies", None)
                or getattr(item, "dependencies", None)
                or []
            ),
            supported_dataset_types=list(
                getattr(instance, "supported_dataset_types", None)
                or getattr(item, "supported_dataset_types", None)
                or []
            ),
            supported_questions=list(
                getattr(instance, "supported_questions", None)
                or getattr(item, "supported_questions", None)
                or []
            ),
            module=getattr(module, "__name__", ""),
            class_name=item.__name__,
            entry_path=entry_path,
        )
        out.append((instance, meta, errs))
        return out


def _slug(text: str) -> str:
    import re

    s = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower())
    return s.strip("_") or "skill"


def is_skippable_module_name(name: str) -> bool:
    base = name.rsplit(".", 1)[-1]
    return base in _SKIP_MODULE_NAMES or base.startswith("_")
