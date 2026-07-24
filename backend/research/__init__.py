"""Autonomous Research Planning — decide which datasets a broad question needs.

Planning only: does NOT retrieve data or modify the existing Planner.
"""

from backend.research.models import (
    AnalysisGoal,
    DatasetNecessity,
    DatasetPriority,
    DatasetRequirement,
    ExpectedOutput,
    ResearchInput,
    ResearchObjective,
    ResearchObjectiveType,
    ResearchPlan,
)
from backend.research.planner import ResearchPlanner
from backend.research.prompts import build_research_plan_prompt
from backend.research.research_agent import (
    AutonomousResearchAgent,
    LLMResearchAgent,
    get_research_agent,
    plan_research,
    reset_research_agent,
    set_research_agent,
)

__all__ = [
    # API
    "plan_research",
    "AutonomousResearchAgent",
    "LLMResearchAgent",
    "ResearchPlanner",
    "get_research_agent",
    "set_research_agent",
    "reset_research_agent",
    "build_research_plan_prompt",
    # Models
    "ResearchPlan",
    "ResearchObjective",
    "ResearchObjectiveType",
    "ResearchInput",
    "DatasetRequirement",
    "DatasetPriority",
    "DatasetNecessity",
    "AnalysisGoal",
    "ExpectedOutput",
]
