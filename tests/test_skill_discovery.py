"""Tests for Automatic Skill Discovery (backend/skills)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.skills import (
    Skill,
    SkillDiscovery,
    SkillMetadata,
    SkillRegistry,
    discover_skills,
    get_skill_registry,
    hot_reload_skills,
    is_valid_skill,
    reset_skill_discovery,
    reset_skill_registry,
    validate_skill_interface,
)
from backend.skills.loader import SkillLoader


@pytest.fixture(autouse=True)
def _reset():
    reset_skill_discovery()
    reset_skill_registry()
    yield
    reset_skill_discovery()
    reset_skill_registry()


# ---------------------------------------------------------------------------
# Skill interface
# ---------------------------------------------------------------------------


class _GoodSkill(Skill):
    name = "Good Skill"
    description = "A valid skill"
    supported_dataset_types = ("tabular",)
    supported_questions = ("analyze", "good")

    def execute(self, **kwargs):
        return {"ok": True}


class _BadSkill(Skill):
    name = "Bad"
    description = "Missing execute body is abstract"
    supported_dataset_types = ("tabular",)
    supported_questions = ("bad",)
    # execute not implemented


class _DuckSkill:
    name = "Duck"
    description = "Duck-typed skill"
    supported_dataset_types = ["time_series"]
    supported_questions = ["forecast duck"]

    def execute(self, **kwargs):
        return "quack"


def test_validate_good_skill():
    assert is_valid_skill(_GoodSkill())
    assert validate_skill_interface(_GoodSkill()) == []


def test_reject_abstract_skill():
    errors = validate_skill_interface(_BadSkill)
    assert errors
    assert any("execute" in e.lower() for e in errors)


def test_duck_typed_skill_valid():
    assert is_valid_skill(_DuckSkill())


def test_skill_matches_question_and_dataset():
    s = _GoodSkill()
    assert s.matches_question("Please analyze GDP")
    assert s.supports_dataset_type("tabular")
    assert not s.supports_dataset_type("text")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_register_and_lookup():
    reg = SkillRegistry()
    reg.register(_GoodSkill())
    assert "good_skill" in reg.list_ids() or "Good Skill".lower().replace(" ", "_") in reg.list_ids()
    ids = reg.list_ids()
    assert len(ids) == 1
    skill_id = ids[0]
    assert reg.get_skill(skill_id) is not None
    assert reg.get(skill_id).metadata.version


def test_registry_rejects_invalid():
    reg = SkillRegistry()
    result = reg.register(_BadSkill, validate=True)
    assert result.valid is False
    assert len(reg) == 0
    assert reg.rejected()


def test_registry_match_question():
    reg = SkillRegistry()
    reg.register(_GoodSkill())
    hits = reg.match_question("analyze something")
    assert hits


# ---------------------------------------------------------------------------
# Discovery of plugins under backend/skills/plugins
# ---------------------------------------------------------------------------


def test_discover_builtin_plugins():
    report = discover_skills(clear_first=True)
    assert report.n_registered >= 3 if hasattr(report, "n_registered") else len(report.registered_ids) >= 3
    ids = set(report.registered_ids)
    assert "forecast" in ids
    assert "correlation" in ids
    assert "visualization" in ids

    reg = get_skill_registry()
    assert "forecast" in reg
    skill = reg.get_skill("forecast")
    assert skill is not None
    out = skill.execute(horizon=3)
    assert out["status"] == "ok"
    assert skill.matches_question("Forecast India's GDP")


def test_metadata_version_and_dependencies():
    report = discover_skills(clear_first=True)
    reg = get_skill_registry()
    meta = reg.get("forecast").metadata
    assert isinstance(meta, SkillMetadata)
    assert meta.version
    assert isinstance(meta.dependencies, list)
    assert meta.supported_dataset_types
    assert meta.supported_questions


def test_reject_invalid_plugin_file(tmp_path: Path):
    bad = tmp_path / "broken_skill.py"
    bad.write_text(
        '''
class NotASkill:
    name = "Nope"
    # missing description, execute, supported_*
''',
        encoding="utf-8",
    )
    reg = SkillRegistry()
    discovery = SkillDiscovery(registry=reg)
    report = discovery.discover_and_register(
        packages=[],  # skip builtin package scan
        paths=[tmp_path],
        clear_first=True,
    )
    # Invalid plain class is ignored (not a Skill) or rejected — never registered
    assert "nope" not in [i.lower() for i in reg.list_ids()]
    assert len(reg) == 0
    # NotASkill is not a Skill subclass and not in SKILL export → nothing extracted
    # Write a Skill subclass missing execute to force rejection
    bad2 = tmp_path / "broken_skill2.py"
    bad2.write_text(
        '''
from backend.skills.base import Skill

class BrokenSkill(Skill):
    name = "Broken"
    description = "no execute"
    supported_dataset_types = ("tabular",)
    supported_questions = ("broken",)
    # execute abstract
''',
        encoding="utf-8",
    )
    report2 = discovery.discover_and_register(packages=[], paths=[tmp_path], clear_first=True)
    assert "broken" not in reg.list_ids()
    assert report2.rejected or len(reg) == 0


def test_valid_plugin_from_path(tmp_path: Path):
    plugin = tmp_path / "custom_skill.py"
    plugin.write_text(
        '''
from backend.skills.base import Skill

class CustomSkill(Skill):
    name = "Custom Outlier"
    description = "Find unusual values"
    version = "2.1.0"
    dependencies = []
    supported_dataset_types = ("tabular",)
    supported_questions = ("outlier", "unusual")
    skill_id = "custom_outlier"

    def execute(self, **kwargs):
        return {"outliers": []}

SKILL = CustomSkill
''',
        encoding="utf-8",
    )
    reg = SkillRegistry()
    discovery = SkillDiscovery(registry=reg)
    report = discovery.discover_and_register(packages=[], paths=[tmp_path], clear_first=True)
    assert "custom_outlier" in report.registered_ids
    assert "custom_outlier" in reg.list_ids()
    meta = reg.get("custom_outlier").metadata
    assert meta.version == "2.1.0"
    assert reg.get_skill("custom_outlier").execute()["outliers"] == []


# ---------------------------------------------------------------------------
# Hot reload
# ---------------------------------------------------------------------------


def test_hot_reload_picks_up_new_plugin(tmp_path: Path):
    reg = SkillRegistry()
    discovery = SkillDiscovery(registry=reg)
    discovery.discover_and_register(packages=["backend.skills.plugins"], clear_first=True)
    before = set(reg.list_ids())

    plugin = tmp_path / "reload_skill.py"
    plugin.write_text(
        '''
from backend.skills.base import Skill

class ReloadSkill(Skill):
    name = "Reload Me"
    description = "Hot reload demo"
    version = "0.1.0"
    supported_dataset_types = ("any",)
    supported_questions = ("reload",)
    skill_id = "reload_me"

    def execute(self, **kwargs):
        return {"reloaded": True}

SKILL = ReloadSkill
''',
        encoding="utf-8",
    )
    report = discovery.hot_reload(packages=["backend.skills.plugins"], paths=[tmp_path])
    assert report.reloaded is True
    assert "reload_me" in reg.list_ids()
    assert "reload_me" in report.registered_ids
    # previous plugins still present
    assert before.issubset(set(reg.list_ids()))


def test_hot_reload_module_api():
    discover_skills(clear_first=True)
    report = hot_reload_skills()
    assert report.reloaded is True
    assert len(report.registered_ids) >= 3


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_loader_extract_from_plugins_module():
    loader = SkillLoader()
    mod = loader.load_module("backend.skills.plugins.forecast_skill")
    items = loader.extract_skills(mod)
    assert items
    instance, meta, errors = items[0]
    assert errors == []
    assert meta is not None
    assert meta.skill_id == "forecast"


def test_planner_facing_registry_stable():
    """Planner later uses get_skill_registry() without code changes."""
    discover_skills(clear_first=True)
    reg = get_skill_registry()
    # Simulate planner lookup
    for skill_id in reg.list_ids():
        skill = reg.get_skill(skill_id)
        assert hasattr(skill, "execute")
        assert hasattr(skill, "name")
        assert hasattr(skill, "description")
        assert hasattr(skill, "supported_dataset_types")
        assert hasattr(skill, "supported_questions")


def test_discovery_report_to_dict():
    report = discover_skills(clear_first=True)
    d = report.to_dict()
    assert "registered_ids" in d
    assert d["n_registered"] == len(report.registered_ids)
