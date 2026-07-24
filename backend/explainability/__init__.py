"""Explainability Layer — structured reasoning for analytical answers.

Does not modify Planner, EDA, Visualization, or Insight generation.
"""

from backend.explainability.explainer import (
    Explainer,
    LLMExplainer,
    RuleBasedExplainer,
    generate_explanation,
    get_default_explainer,
    reset_default_explainer,
    set_default_explainer,
)
from backend.explainability.models import (
    DatasetCitation,
    ExplanationInput,
    ExplanationResult,
    ExplanationStyle,
    FilterExplanation,
    JoinExplanation,
    ToolStepExplanation,
)
from backend.explainability.templates import (
    build_llm_explanation_prompt,
    build_reasoning_summary,
    render_detailed,
    render_short,
    render_technical,
)

__all__ = [
    # API
    "generate_explanation",
    "Explainer",
    "RuleBasedExplainer",
    "LLMExplainer",
    "get_default_explainer",
    "set_default_explainer",
    "reset_default_explainer",
    # Models
    "ExplanationResult",
    "ExplanationInput",
    "ExplanationStyle",
    "DatasetCitation",
    "JoinExplanation",
    "ToolStepExplanation",
    "FilterExplanation",
    # Templates
    "render_short",
    "render_detailed",
    "render_technical",
    "build_reasoning_summary",
    "build_llm_explanation_prompt",
]
