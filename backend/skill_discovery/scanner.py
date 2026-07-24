"""Scanners that find analytical skills from modules, manifests, and entry points."""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
import re
from pathlib import Path
from typing import Any, Iterable, Optional

from backend.core.logger import get_logger
from backend.skill_discovery.decorators import get_declared_skills
from backend.skill_discovery.models import DiscoveredSkill, SkillSource

logger = get_logger(__name__)

# Convention: agent modules → skill metadata
AGENT_SKILL_MAP: dict[str, dict[str, Any]] = {
    "forecasting_agent": {
        "skill_id": "forecast",
        "name": "Forecast",
        "category": "predictive",
        "keywords": ["forecast", "predict", "prediction", "future"],
        "intents": ["forecasting", "predictive"],
        "produces_chart": True,
        "priority": 20,
    },
    "viz_agent": {
        "skill_id": "visualization",
        "name": "Visualization",
        "category": "visualization",
        "keywords": ["visualize", "plot", "chart", "graph"],
        "intents": ["visualization"],
        "produces_chart": True,
        "priority": 80,
    },
    "comparison_agent": {
        "skill_id": "comparison",
        "name": "Comparison",
        "category": "general",
        "keywords": ["compare", "comparison", "versus", "vs"],
        "intents": ["comparison"],
        "produces_chart": True,
        "priority": 42,
    },
    "eda_agent": {
        "skill_id": "eda_summary",
        "name": "EDA Summary",
        "category": "descriptive",
        "keywords": ["analyze", "explore", "eda", "summary"],
        "intents": ["eda"],
        "produces_chart": False,
        "priority": 90,
    },
    "pattern_detection_agent": {
        "skill_id": "pattern_detection",
        "name": "Pattern Detection",
        "category": "descriptive",
        "keywords": ["pattern", "anomaly pattern", "detect patterns"],
        "intents": ["eda", "statistical_analysis"],
        "produces_chart": False,
        "priority": 70,
    },
    "hypothesis_agent": {
        "skill_id": "hypothesis_testing",
        "name": "Hypothesis Testing",
        "category": "inference",
        "keywords": ["hypothesis", "significant", "p-value"],
        "intents": ["statistical_analysis", "inference"],
        "produces_chart": False,
        "priority": 55,
    },
    "insight_agent": {
        "skill_id": "insight_generation",
        "name": "Insight Generation",
        "category": "descriptive",
        "keywords": ["insight", "explain", "summary insight"],
        "intents": ["explanation", "eda"],
        "produces_chart": False,
        "priority": 85,
    },
    "chart_interpretation_agent": {
        "skill_id": "chart_interpretation",
        "name": "Chart Interpretation",
        "category": "visualization",
        "keywords": ["interpret chart", "explain chart", "chart meaning"],
        "intents": ["visualization", "explanation"],
        "produces_chart": False,
        "priority": 75,
    },
    "qa_agent": {
        "skill_id": "qa",
        "name": "Q&A",
        "category": "general",
        "keywords": ["question", "answer", "qa", "ask"],
        "intents": ["explanation"],
        "produces_chart": False,
        "priority": 88,
    },
    "recommendation_agent": {
        "skill_id": "recommendation",
        "name": "Recommendations",
        "category": "general",
        "keywords": ["recommend", "next steps", "suggestion"],
        "intents": ["explanation"],
        "produces_chart": False,
        "priority": 92,
    },
    "cleaning_agent": {
        "skill_id": "data_cleaning",
        "name": "Data Cleaning",
        "category": "descriptive",
        "keywords": ["clean", "cleaning", "missing values"],
        "intents": ["eda"],
        "produces_chart": False,
        "priority": 60,
    },
}

# Skip non-analytical infrastructure agents
AGENT_SKIP = frozenset(
    {
        "planner_agent",
        "conversation_context_agent",
        "data_agent",
        "data_engineer_agent",
        "dataset_retrieve_agent",
        "dataset_prepare_agent",
        "dataset_search_agent",
        "dataset_topic_agent",
        "dataset_profile_agent",
        "dataset_insight_agent",
        "dataset_embedding_search_agent",
        "decision_agent",
        "intent_agent",
        "evaluation_agent",
    }
)


class SkillScanner:
    """Discover skills from multiple sources."""

    def scan_decorators(self) -> list[DiscoveredSkill]:
        skills: list[DiscoveredSkill] = []
        for entry in get_declared_skills():
            skills.append(
                DiscoveredSkill(
                    skill_id=str(entry["skill_id"]),
                    name=str(entry.get("name") or entry["skill_id"]),
                    description=str(entry.get("description") or ""),
                    category=str(entry.get("category") or "general"),
                    keywords=list(entry.get("keywords") or []),
                    intents=list(entry.get("intents") or []),
                    tags=list(entry.get("tags") or []),
                    produces_chart=bool(entry.get("produces_chart")),
                    priority=int(entry.get("priority") or 100),
                    enabled=bool(entry.get("enabled", True)),
                    version=str(entry.get("version") or "1.0"),
                    source=SkillSource.DECORATOR,
                    module=str(entry.get("module") or ""),
                    callable_name=str(entry.get("callable_name") or ""),
                    handler=entry.get("handler"),
                    metadata=dict(entry.get("metadata") or {}),
                )
            )
        return skills

    def scan_agent_package(
        self,
        package_name: str = "backend.agents",
    ) -> list[DiscoveredSkill]:
        """Discover skills from agent modules via convention map + docstrings."""
        skills: list[DiscoveredSkill] = []
        try:
            pkg = importlib.import_module(package_name)
        except Exception as exc:
            logger.warning("Cannot import agent package", extra={"pkg": package_name, "error": str(exc)})
            return skills

        paths = getattr(pkg, "__path__", None)
        if not paths:
            return skills

        for modinfo in pkgutil.iter_modules(paths):
            short = modinfo.name  # e.g. forecasting_agent
            if short.startswith("_") or short in AGENT_SKIP:
                continue
            full = f"{package_name}.{short}"
            try:
                module = importlib.import_module(full)
            except Exception as exc:
                logger.debug("Skip agent module", extra={"module": full, "error": str(exc)})
                continue

            meta = AGENT_SKILL_MAP.get(short)
            if meta:
                skill = DiscoveredSkill(
                    skill_id=str(meta["skill_id"]),
                    name=str(meta["name"]),
                    description=str(
                        meta.get("description")
                        or (inspect.getdoc(module) or f"Agent skill from {short}")
                    ).split("\n")[0],
                    category=str(meta.get("category") or "general"),
                    keywords=list(meta.get("keywords") or []),
                    intents=list(meta.get("intents") or []),
                    tags=["agent", short],
                    produces_chart=bool(meta.get("produces_chart")),
                    priority=int(meta.get("priority") or 100),
                    source=SkillSource.AGENT_MODULE,
                    module=full,
                    callable_name=_find_agent_callable(module, short),
                    metadata={"agent_module": short},
                )
                # Attach handler if found
                if skill.callable_name and hasattr(module, skill.callable_name):
                    skill.handler = getattr(module, skill.callable_name)
                skills.append(skill)
                continue

            # Unmapped agent modules: derive a generic skill if public *agent* function exists
            callable_name = _find_agent_callable(module, short)
            if not callable_name:
                continue
            sid = short.replace("_agent", "").replace("_", "-")
            skills.append(
                DiscoveredSkill(
                    skill_id=sid,
                    name=sid.replace("-", " ").replace("_", " ").title(),
                    description=(inspect.getdoc(getattr(module, callable_name)) or f"Discovered from {short}").split(
                        "\n"
                    )[0],
                    category="general",
                    keywords=[sid.replace("-", " "), short.replace("_", " ")],
                    tags=["agent", "auto", short],
                    source=SkillSource.AGENT_MODULE,
                    module=full,
                    callable_name=callable_name,
                    handler=getattr(module, callable_name, None),
                    priority=95,
                    metadata={"agent_module": short, "auto_mapped": True},
                )
            )
        return skills

    def scan_manifests(
        self,
        paths: Iterable[str | Path],
    ) -> list[DiscoveredSkill]:
        """Load skill manifests (JSON) from files or directories."""
        skills: list[DiscoveredSkill] = []
        for p in paths:
            path = Path(p)
            if not path.exists():
                continue
            files: list[Path] = []
            if path.is_file():
                files = [path]
            else:
                files = list(path.rglob("skill_manifest.json")) + list(
                    path.rglob("*_skills.json")
                )
            for fp in files:
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                except Exception as exc:
                    logger.warning("Invalid skill manifest", extra={"path": str(fp), "error": str(exc)})
                    continue
                items = data if isinstance(data, list) else data.get("skills") or data.get("tools") or [data]
                if not isinstance(items, list):
                    items = [items]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    skill = DiscoveredSkill.from_dict(item)
                    if not skill.skill_id:
                        continue
                    skill.source = SkillSource.MANIFEST
                    skill.manifest_path = str(fp)
                    skills.append(skill)
        return skills

    def scan_entry_points(self, group: str = "analytics_copilot.skills") -> list[DiscoveredSkill]:
        """Discover skills registered via package entry points (plugins)."""
        skills: list[DiscoveredSkill] = []
        try:
            from importlib import metadata
        except ImportError:  # pragma: no cover
            return skills

        try:
            eps = metadata.entry_points()
            # Python 3.10+ SelectableGroups vs dict
            if hasattr(eps, "select"):
                selected = list(eps.select(group=group))
            else:  # pragma: no cover
                selected = list(eps.get(group, []))  # type: ignore[arg-type]
        except Exception as exc:
            logger.debug("entry_points scan failed", extra={"error": str(exc)})
            return skills

        for ep in selected:
            try:
                loaded = ep.load()
            except Exception as exc:
                logger.warning("Failed loading entry point", extra={"ep": ep.name, "error": str(exc)})
                continue
            skill = _skill_from_loaded(ep.name, loaded, source=SkillSource.ENTRY_POINT)
            if skill:
                skill.entry_point = f"{group}:{ep.name}"
                skills.append(skill)
        return skills

    def scan_module_attributes(
        self,
        module_name: str,
        *,
        attr_names: tuple[str, ...] = ("SKILLS", "TOOLS", "ANALYTICAL_SKILLS"),
    ) -> list[DiscoveredSkill]:
        """Discover list/dict skill declarations exported by a module."""
        skills: list[DiscoveredSkill] = []
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            logger.debug("scan_module_attributes import failed", extra={"mod": module_name, "error": str(exc)})
            return skills

        for attr in attr_names:
            if not hasattr(module, attr):
                continue
            raw = getattr(module, attr)
            items: list[Any]
            if isinstance(raw, dict):
                items = list(raw.values()) if all(isinstance(v, dict) for v in raw.values()) else [raw]
            elif isinstance(raw, (list, tuple)):
                items = list(raw)
            else:
                continue
            for item in items:
                if isinstance(item, DiscoveredSkill):
                    skills.append(item)
                elif isinstance(item, dict):
                    s = DiscoveredSkill.from_dict(item)
                    if s.skill_id:
                        s.source = SkillSource.CUSTOM_PATH
                        s.module = module_name
                        skills.append(s)
                elif callable(item) and hasattr(item, "__analytical_skill__"):
                    meta = getattr(item, "__analytical_skill__")
                    s = DiscoveredSkill.from_dict(meta)
                    s.handler = item
                    s.source = SkillSource.DECORATOR
                    skills.append(s)
        return skills


def _find_agent_callable(module: Any, short_name: str) -> str:
    # Prefer exact name match
    if hasattr(module, short_name) and callable(getattr(module, short_name)):
        return short_name
    # Any public function ending with _agent
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("_"):
            continue
        if name.endswith("_agent") or name == short_name:
            return name
    return ""


def _skill_from_loaded(
    name: str,
    loaded: Any,
    *,
    source: SkillSource,
) -> Optional[DiscoveredSkill]:
    if isinstance(loaded, DiscoveredSkill):
        loaded.source = source
        return loaded
    if isinstance(loaded, dict):
        s = DiscoveredSkill.from_dict(loaded)
        s.source = source
        if not s.skill_id:
            s.skill_id = name
        return s if s.skill_id else None
    if callable(loaded):
        meta = getattr(loaded, "__analytical_skill__", None)
        if isinstance(meta, dict):
            s = DiscoveredSkill.from_dict(meta)
            s.handler = loaded
            s.source = source
            return s
        # bare callable
        return DiscoveredSkill(
            skill_id=name,
            name=name.replace("_", " ").title(),
            description=(inspect.getdoc(loaded) or "").split("\n")[0],
            source=source,
            callable_name=getattr(loaded, "__name__", name),
            module=getattr(loaded, "__module__", ""),
            handler=loaded,
            keywords=[name.replace("_", " ")],
        )
    return None
