"""Automatic skill discovery — scan, validate, register, hot-reload."""

from __future__ import annotations

import pkgutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from backend.core.logger import get_logger
from backend.skills.loader import SkillLoader, is_skippable_module_name
from backend.skills.metadata import SkillMetadata, SkillRegistration
from backend.skills.registry import SkillRegistry, get_skill_registry

logger = get_logger(__name__)

# Default plugin roots relative to this package
SKILLS_PACKAGE = "backend.skills"
PLUGINS_PACKAGE = "backend.skills.plugins"
SKILLS_DIR = Path(__file__).resolve().parent


@dataclass
class DiscoveryReport:
    """Result of a discovery / hot-reload pass."""

    registered_ids: list[str] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    modules_scanned: list[str] = field(default_factory=list)
    paths_scanned: list[str] = field(default_factory=list)
    reloaded: bool = False
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "registered_ids": list(self.registered_ids),
            "rejected": list(self.rejected),
            "errors": list(self.errors),
            "modules_scanned": list(self.modules_scanned),
            "paths_scanned": list(self.paths_scanned),
            "reloaded": self.reloaded,
            "duration_seconds": self.duration_seconds,
            "n_registered": len(self.registered_ids),
            "n_rejected": len(self.rejected),
        }


class SkillDiscovery:
    """
    Scan backend/skills (and plugin subpackages), validate, auto-register.

    Planner later uses SkillRegistry without depending on this class.
    """

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        loader: SkillLoader | None = None,
    ):
        # Empty SkillRegistry is falsy (__len__==0); never use `registry or ...`
        self._registry = registry if registry is not None else get_skill_registry()
        self._loader = loader or SkillLoader()
        self._loaded_modules: list[str] = []

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    def discover_and_register(
        self,
        *,
        packages: Sequence[str] | None = None,
        paths: Sequence[str | Path] | None = None,
        replace: bool = True,
        clear_first: bool = False,
    ) -> DiscoveryReport:
        """
        Full discovery pipeline:
          scan → load → validate interface → register valid / reject invalid
        """
        t0 = time.perf_counter()
        report = DiscoveryReport()

        if clear_first:
            self._registry.clear()

        # None → default plugin package; explicit [] means "no packages"
        if packages is None:
            packages = [PLUGINS_PACKAGE]
        else:
            packages = list(packages)

        for pkg in packages:
            self._scan_package(pkg, report=report, replace=replace)

        # Optional filesystem paths (hot-drop plugin files)
        for p in paths or []:
            self._scan_path(Path(p), report=report, replace=replace)

        report.duration_seconds = round(time.perf_counter() - t0, 4)
        logger.info(
            "Skill discovery finished",
            extra={
                "registered": len(report.registered_ids),
                "rejected": len(report.rejected),
                "errors": len(report.errors),
                "seconds": report.duration_seconds,
            },
        )
        return report

    def hot_reload(
        self,
        *,
        packages: Sequence[str] | None = None,
        paths: Sequence[str | Path] | None = None,
    ) -> DiscoveryReport:
        """
        Re-scan and re-register skills (replace existing ids).

        Does not require process restart for newly added plugin modules
        that are importable / on disk paths.
        """
        # Reload previously loaded modules when possible
        for mod_name in list(self._loaded_modules):
            try:
                self._loader.reload_module(mod_name)
            except Exception as exc:
                logger.debug("hot_reload module failed", extra={"mod": mod_name, "error": str(exc)})

        report = self.discover_and_register(
            packages=packages,
            paths=paths,
            replace=True,
            clear_first=False,
        )
        report.reloaded = True
        return report

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _scan_package(self, package_name: str, *, report: DiscoveryReport, replace: bool) -> None:
        try:
            pkg = self._loader.load_module(package_name)
        except Exception as exc:
            # Package may not exist yet — not fatal
            report.errors.append(f"package {package_name}: {exc}")
            return

        report.modules_scanned.append(package_name)
        if package_name not in self._loaded_modules:
            self._loaded_modules.append(package_name)

        # Skills declared on package itself
        self._register_from_module(pkg, entry_path="", report=report, replace=replace)

        paths = getattr(pkg, "__path__", None)
        if not paths:
            return

        import pkgutil

        for modinfo in pkgutil.iter_modules(paths):
            short = modinfo.name
            if is_skippable_module_name(short):
                continue
            full = f"{package_name}.{short}"
            try:
                module = self._loader.load_module(full)
            except Exception as exc:
                report.errors.append(f"import {full}: {exc}")
                continue
            report.modules_scanned.append(full)
            if full not in self._loaded_modules:
                self._loaded_modules.append(full)
            self._register_from_module(module, entry_path="", report=report, replace=replace)

    def _scan_path(self, path: Path, *, report: DiscoveryReport, replace: bool) -> None:
        path = Path(path)
        if not path.exists():
            report.errors.append(f"path not found: {path}")
            return
        report.paths_scanned.append(str(path))

        files: list[Path]
        if path.is_file() and path.suffix == ".py":
            files = [path]
        else:
            files = sorted(path.glob("*.py"))

        for fp in files:
            if fp.name.startswith("_") or fp.stem in {
                "base",
                "metadata",
                "registry",
                "loader",
                "discovery",
            }:
                continue
            try:
                module = self._loader.load_module_from_path(fp)
            except Exception as exc:
                report.errors.append(f"load {fp}: {exc}")
                continue
            report.modules_scanned.append(getattr(module, "__name__", str(fp)))
            self._register_from_module(
                module,
                entry_path=str(fp),
                report=report,
                replace=replace,
            )

    def _register_from_module(
        self,
        module: Any,
        *,
        entry_path: str,
        report: DiscoveryReport,
        replace: bool,
    ) -> None:
        try:
            candidates = self._loader.extract_skills(module, entry_path=entry_path)
        except Exception as exc:
            report.errors.append(f"extract {getattr(module, '__name__', '?')}: {exc}")
            return

        for instance, meta, errors in candidates:
            if errors:
                payload = {
                    "module": getattr(module, "__name__", ""),
                    "class": type(instance).__name__,
                    "errors": errors,
                    "metadata": meta.to_dict() if meta else {},
                }
                report.rejected.append(payload)
                self._registry.record_rejection(
                    skill_id=meta.skill_id if meta else "",
                    name=meta.name if meta else type(instance).__name__,
                    reason="; ".join(errors),
                    metadata=meta,
                    extra={"module": payload["module"], "class": payload["class"]},
                )
                continue

            try:
                reg = self._registry.register(
                    instance,
                    metadata=meta,
                    replace=replace,
                    validate=True,
                )
            except Exception as exc:
                report.errors.append(f"register: {exc}")
                continue

            if reg.valid:
                report.registered_ids.append(reg.metadata.skill_id)
            else:
                report.rejected.append(reg.to_dict())


# ---------------------------------------------------------------------------
# Module API
# ---------------------------------------------------------------------------

_default_discovery: SkillDiscovery | None = None


def get_skill_discovery(registry: SkillRegistry | None = None) -> SkillDiscovery:
    global _default_discovery
    if registry is not None:
        return SkillDiscovery(registry=registry)
    if _default_discovery is None:
        _default_discovery = SkillDiscovery(registry=get_skill_registry())
    return _default_discovery


def reset_skill_discovery() -> None:
    global _default_discovery
    _default_discovery = None


def discover_skills(**kwargs: Any) -> DiscoveryReport:
    """Scan backend/skills plugins and register into the default SkillRegistry."""
    return get_skill_discovery().discover_and_register(**kwargs)


def hot_reload_skills(**kwargs: Any) -> DiscoveryReport:
    """Hot-reload skill plugins into the default SkillRegistry."""
    return get_skill_discovery().hot_reload(**kwargs)
