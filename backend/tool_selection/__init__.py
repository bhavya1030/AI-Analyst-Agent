"""Dynamic Tool Selection — choose analytical tools for a user question.

Planner later calls select_tools(); not integrated into LangGraph yet.
Does not modify Planner, EDA, Visualization, or existing analytical tools.
"""

from backend.tool_selection.models import (
    BuiltinTool,
    ExecutionPlan,
    SelectedTool,
    Tool,
    ToolCategory,
    ToolSelectionInput,
    ToolSpec,
)
from backend.tool_selection.prompts import build_tool_selection_prompt
from backend.tool_selection.registry import (
    ToolRegistry,
    ToolRegistryError,
    build_default_tools,
    create_default_registry,
    get_default_registry,
    reset_default_registry,
    set_default_registry,
)
from backend.tool_selection.selector import (
    LLMToolSelector,
    RuleBasedToolSelector,
    ToolSelector,
    extract_profile_signals,
    get_default_selector,
    reset_default_selector,
    select_tools,
    set_default_selector,
)

__all__ = [
    # API
    "select_tools",
    "ToolSelector",
    "RuleBasedToolSelector",
    "LLMToolSelector",
    "get_default_selector",
    "set_default_selector",
    "reset_default_selector",
    # Registry
    "ToolRegistry",
    "ToolRegistryError",
    "get_default_registry",
    "set_default_registry",
    "reset_default_registry",
    "create_default_registry",
    "build_default_tools",
    # Models
    "Tool",
    "ToolSpec",
    "BuiltinTool",
    "ToolCategory",
    "ToolSelectionInput",
    "SelectedTool",
    "ExecutionPlan",
    "extract_profile_signals",
    "build_tool_selection_prompt",
]
