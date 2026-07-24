"""Decorators for declaring analytical skills discoverable at import time."""

from __future__ import annotations

from typing import Any, Callable, Optional

# Global registry of decorator-declared skills (module import side-effect)
_DECLARED_SKILLS: list[dict[str, Any]] = []


def analytical_skill(
    skill_id: str | None = None,
    *,
    name: str | None = None,
    description: str = "",
    category: str = "general",
    keywords: list[str] | None = None,
    intents: list[str] | None = None,
    tags: list[str] | None = None,
    produces_chart: bool = False,
    priority: int = 100,
    enabled: bool = True,
    version: str = "1.0",
    **metadata: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Mark a function as an analytical skill for automatic discovery.

    Example:
        @analytical_skill("my_outlier", category="anomaly", keywords=["outlier"])
        def my_outlier_tool(...):
            ...
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        sid = (skill_id or getattr(fn, "__name__", "skill")).strip()
        display = name or sid.replace("_", " ").title()
        entry = {
            "skill_id": sid,
            "name": display,
            "description": description or (fn.__doc__ or "").strip().split("\n")[0],
            "category": category,
            "keywords": list(keywords or [sid.replace("_", " ")]),
            "intents": list(intents or []),
            "tags": list(tags or []),
            "produces_chart": produces_chart,
            "priority": priority,
            "enabled": enabled,
            "version": version,
            "module": getattr(fn, "__module__", "") or "",
            "callable_name": getattr(fn, "__name__", "") or "",
            "handler": fn,
            "metadata": dict(metadata),
        }
        # Avoid duplicates on re-import
        _DECLARED_SKILLS[:] = [s for s in _DECLARED_SKILLS if s.get("skill_id") != sid]
        _DECLARED_SKILLS.append(entry)
        # Attach metadata on function for scanners
        setattr(fn, "__analytical_skill__", entry)
        return fn

    return decorator


# Alias
skill = analytical_skill


def get_declared_skills() -> list[dict[str, Any]]:
    """Return copies of decorator-declared skill metadata."""
    return [dict(s) for s in _DECLARED_SKILLS]


def clear_declared_skills() -> None:
    """Test helper."""
    _DECLARED_SKILLS.clear()
