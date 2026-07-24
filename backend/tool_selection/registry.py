"""Tool registry — built-in analytical tools + plugin registration."""

from __future__ import annotations

import threading
from typing import Iterable, Optional, Sequence

from backend.core.logger import get_logger
from backend.tool_selection.models import (
    BuiltinTool,
    Tool,
    ToolCategory,
    ToolSpec,
)

logger = get_logger(__name__)


class ToolRegistryError(Exception):
    """Registry operation failed."""


class ToolRegistry:
    """
    Registry of analytical tools available for selection.

    Supports future plugins via register() / register_spec() without
    changing the selector API.
    """

    def __init__(self, tools: Optional[Sequence[Tool]] = None):
        self._lock = threading.RLock()
        self._tools: dict[str, Tool] = {}
        if tools:
            for t in tools:
                self.register(t, replace=True)

    def register(self, tool: Tool, *, replace: bool = False) -> None:
        if tool is None or not tool.spec or not tool.spec.tool_id:
            raise ToolRegistryError("Tool must have a non-empty tool_id")
        tid = tool.spec.tool_id.strip()
        with self._lock:
            if tid in self._tools and not replace:
                raise ToolRegistryError(f"Tool already registered: {tid}")
            self._tools[tid] = tool
            logger.debug("Registered tool", extra={"tool_id": tid, "plugin": tool.spec.is_plugin})

    def register_spec(self, spec: ToolSpec | dict, *, replace: bool = False) -> Tool:
        """Register from ToolSpec / dict (plugin-friendly)."""
        if isinstance(spec, dict):
            spec = ToolSpec.from_dict(spec)
        if not isinstance(spec, ToolSpec):
            raise ToolRegistryError("spec must be ToolSpec or dict")
        tool = BuiltinTool.from_spec(spec)
        self.register(tool, replace=replace)
        return tool

    def unregister(self, tool_id: str) -> bool:
        tid = (tool_id or "").strip()
        with self._lock:
            if tid not in self._tools:
                return False
            del self._tools[tid]
            return True

    def get(self, tool_id: str) -> Optional[Tool]:
        with self._lock:
            return self._tools.get((tool_id or "").strip())

    def list_tools(self, *, enabled_only: bool = True) -> list[Tool]:
        with self._lock:
            tools = list(self._tools.values())
        if enabled_only:
            tools = [t for t in tools if t.spec.enabled]
        return sorted(tools, key=lambda t: (t.spec.priority, t.spec.tool_id))

    def list_specs(self, *, enabled_only: bool = True) -> list[ToolSpec]:
        return [t.spec for t in self.list_tools(enabled_only=enabled_only)]

    def list_ids(self, *, enabled_only: bool = True) -> list[str]:
        return [t.spec.tool_id for t in self.list_tools(enabled_only=enabled_only)]

    def by_category(self, category: ToolCategory | str) -> list[Tool]:
        if isinstance(category, str):
            try:
                category = ToolCategory(category)
            except ValueError:
                return []
        return [t for t in self.list_tools() if t.spec.category == category]

    def clear(self) -> None:
        with self._lock:
            self._tools.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)

    def __contains__(self, tool_id: str) -> bool:
        with self._lock:
            return (tool_id or "").strip() in self._tools


def build_default_tools() -> list[Tool]:
    """Built-in analytical tool catalog (selection metadata only)."""
    specs: list[ToolSpec] = [
        ToolSpec(
            tool_id="correlation",
            name="Correlation",
            description="Measure linear/monotonic relationships between numeric variables.",
            category=ToolCategory.RELATIONSHIP,
            keywords=[
                "correlation",
                "correlate",
                "relationship",
                "related",
                "association",
                "vs",
                "versus",
                "between",
                "heatmap",
            ],
            intents=["statistical_analysis", "comparison", "relationship"],
            requires=["multi_numeric"],
            prefers=["tabular"],
            tags=["stats", "relationship"],
            produces_chart=True,
            priority=40,
        ),
        ToolSpec(
            tool_id="regression",
            name="Regression",
            description="Fit regression models to explain or predict a target from predictors.",
            category=ToolCategory.RELATIONSHIP,
            keywords=[
                "regression",
                "predict",
                "explain",
                "impact of",
                "effect of",
                "dependent",
                "independent",
                "linear model",
                "relationship between",
            ],
            intents=["statistical_analysis", "relationship", "predictive"],
            requires=["multi_numeric"],
            prefers=["tabular"],
            tags=["stats", "model"],
            produces_chart=True,
            priority=45,
        ),
        ToolSpec(
            tool_id="forecast",
            name="Forecast",
            description="Forecast future values of a time-dependent metric.",
            category=ToolCategory.PREDICTIVE,
            keywords=[
                "forecast",
                "predict",
                "prediction",
                "next years",
                "next months",
                "future",
                "projection",
                "horizon",
            ],
            intents=["forecasting", "predictive"],
            requires=["time"],
            prefers=["time_series", "numeric_metric"],
            tags=["forecast", "time"],
            produces_chart=True,
            priority=20,
        ),
        ToolSpec(
            tool_id="trend",
            name="Trend",
            description="Detect and describe trends over time.",
            category=ToolCategory.TIME_SERIES,
            keywords=[
                "trend",
                "growth",
                "decline",
                "over time",
                "trajectory",
                "increase",
                "decrease",
                "historical",
            ],
            intents=["visualization", "eda", "time_series"],
            requires=["time"],
            prefers=["time_series", "numeric_metric"],
            tags=["time", "eda"],
            produces_chart=True,
            priority=30,
        ),
        ToolSpec(
            tool_id="time_series",
            name="Time Series",
            description="General time-series analysis (patterns, levels, changes).",
            category=ToolCategory.TIME_SERIES,
            keywords=[
                "time series",
                "timeseries",
                "temporal",
                "over years",
                "monthly",
                "annual",
                "daily",
            ],
            intents=["time_series", "eda", "forecasting"],
            requires=["time"],
            prefers=["time_series"],
            tags=["time"],
            produces_chart=True,
            priority=35,
        ),
        ToolSpec(
            tool_id="seasonality",
            name="Seasonality",
            description="Detect seasonal / periodic patterns in time series.",
            category=ToolCategory.TIME_SERIES,
            keywords=[
                "seasonality",
                "seasonal",
                "cycle",
                "periodic",
                "monthly pattern",
                "quarterly",
                "recurring",
            ],
            intents=["time_series", "statistical_analysis"],
            requires=["time"],
            prefers=["time_series"],
            tags=["time", "pattern"],
            produces_chart=True,
            priority=50,
        ),
        ToolSpec(
            tool_id="distribution",
            name="Distribution",
            description="Analyze value distributions (shape, spread, modes).",
            category=ToolCategory.DISTRIBUTION,
            keywords=[
                "distribution",
                "histogram",
                "density",
                "spread",
                "skew",
                "how distributed",
                "frequency",
            ],
            intents=["eda", "statistical_analysis", "visualization"],
            prefers=["numeric_metric"],
            tags=["eda", "stats"],
            produces_chart=True,
            priority=55,
        ),
        ToolSpec(
            tool_id="outlier_detection",
            name="Outlier Detection",
            description="Find unusual or anomalous values in the dataset.",
            category=ToolCategory.ANOMALY,
            keywords=[
                "outlier",
                "outliers",
                "anomaly",
                "anomalies",
                "unusual",
                "abnormal",
                "strange values",
                "extreme values",
                "spike",
            ],
            intents=["statistical_analysis", "eda", "anomaly"],
            prefers=["numeric_metric"],
            tags=["anomaly", "eda"],
            produces_chart=True,
            priority=25,
        ),
        ToolSpec(
            tool_id="clustering",
            name="Clustering",
            description="Group similar observations into clusters.",
            category=ToolCategory.CLUSTERING,
            keywords=[
                "cluster",
                "clustering",
                "segment",
                "segmentation",
                "group similar",
                "kmeans",
                "k-means",
            ],
            intents=["statistical_analysis", "clustering"],
            requires=["multi_numeric"],
            prefers=["tabular", "large_n"],
            tags=["unsupervised"],
            produces_chart=True,
            priority=60,
        ),
        ToolSpec(
            tool_id="hypothesis_testing",
            name="Hypothesis Testing",
            description="Statistical hypothesis tests (t-test, chi-square, etc.).",
            category=ToolCategory.INFERENCE,
            keywords=[
                "hypothesis",
                "significant",
                "significance",
                "p-value",
                "p value",
                "t-test",
                "chi-square",
                "statistically",
                "null hypothesis",
            ],
            intents=["statistical_analysis", "inference"],
            prefers=["numeric_metric", "categorical"],
            tags=["stats", "inference"],
            produces_chart=False,
            priority=55,
        ),
        ToolSpec(
            tool_id="anova",
            name="ANOVA",
            description="Compare means across groups (analysis of variance).",
            category=ToolCategory.INFERENCE,
            keywords=[
                "anova",
                "analysis of variance",
                "compare groups",
                "group means",
                "between groups",
            ],
            intents=["statistical_analysis", "comparison", "inference"],
            requires=["numeric_metric", "categorical"],
            prefers=["tabular"],
            tags=["stats", "inference"],
            produces_chart=True,
            priority=58,
        ),
        ToolSpec(
            tool_id="pca",
            name="PCA",
            description="Principal component analysis for dimensionality reduction.",
            category=ToolCategory.DIMENSIONALITY,
            keywords=[
                "pca",
                "principal component",
                "dimensionality",
                "reduce dimensions",
                "components",
                "variance explained",
            ],
            intents=["statistical_analysis", "dimensionality"],
            requires=["multi_numeric"],
            prefers=["tabular", "large_n"],
            tags=["unsupervised", "dimensionality"],
            produces_chart=True,
            priority=65,
        ),
        ToolSpec(
            tool_id="histogram",
            name="Histogram",
            description="Plot a histogram of a numeric variable.",
            category=ToolCategory.VISUALIZATION,
            keywords=[
                "histogram",
                "hist",
                "bin",
                "frequency plot",
            ],
            intents=["visualization", "distribution"],
            prefers=["numeric_metric"],
            tags=["chart"],
            produces_chart=True,
            priority=70,
        ),
        ToolSpec(
            tool_id="scatter_plot",
            name="Scatter Plot",
            description="Scatter plot to visualize bivariate relationships.",
            category=ToolCategory.VISUALIZATION,
            keywords=[
                "scatter",
                "scatter plot",
                "scatterplot",
                "xy plot",
                "plot against",
            ],
            intents=["visualization", "relationship"],
            requires=["multi_numeric"],
            prefers=["tabular"],
            tags=["chart", "relationship"],
            produces_chart=True,
            priority=48,
        ),
        ToolSpec(
            tool_id="visualization",
            name="Visualization",
            description="General charting / visualization of selected metrics.",
            category=ToolCategory.VISUALIZATION,
            keywords=[
                "visualize",
                "visualise",
                "plot",
                "chart",
                "graph",
                "show",
                "display",
                "draw",
            ],
            intents=["visualization"],
            prefers=["numeric_metric", "time"],
            tags=["chart"],
            produces_chart=True,
            priority=80,
        ),
        ToolSpec(
            tool_id="comparison",
            name="Comparison",
            description="Compare metrics across entities (countries, groups, series).",
            category=ToolCategory.GENERAL,
            keywords=[
                "compare",
                "comparison",
                "versus",
                "vs",
                "difference between",
                "against",
            ],
            intents=["comparison"],
            prefers=["entity", "multi_metric", "numeric_metric"],
            tags=["eda", "compare"],
            produces_chart=True,
            priority=42,
        ),
        ToolSpec(
            tool_id="eda_summary",
            name="EDA Summary",
            description="Exploratory overview when the question is broad or generic.",
            category=ToolCategory.DESCRIPTIVE,
            keywords=[
                "analyze",
                "analyse",
                "explore",
                "overview",
                "summary",
                "describe",
                "eda",
                "profile",
            ],
            intents=["eda", "explanation"],
            tags=["eda", "default"],
            produces_chart=False,
            priority=90,
        ),
    ]
    return [BuiltinTool.from_spec(s) for s in specs]


def create_default_registry() -> ToolRegistry:
    """Fresh registry preloaded with built-in tools."""
    return ToolRegistry(tools=build_default_tools())


# Process-wide default registry (plugins can register into this)
_default_registry: ToolRegistry | None = None
_registry_lock = threading.Lock()


def get_default_registry() -> ToolRegistry:
    global _default_registry
    with _registry_lock:
        if _default_registry is None:
            _default_registry = create_default_registry()
        return _default_registry


def set_default_registry(registry: ToolRegistry) -> None:
    global _default_registry
    with _registry_lock:
        _default_registry = registry


def reset_default_registry() -> None:
    """Test helper: rebuild default catalog."""
    global _default_registry
    with _registry_lock:
        _default_registry = create_default_registry()
