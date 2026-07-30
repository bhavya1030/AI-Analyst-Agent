"""Automatic chart selection and axis / aggregation inference (Visualization v2)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Sequence

import pandas as pd

# Chart families supported end-to-end
CHART_TYPES = frozenset(
    {"scatter", "line", "histogram", "pie", "heatmap", "bar", "box", "visualization"}
)

_TIME_NAME_RE = re.compile(
    r"(^|_)(year|date|time|month|day|week|timestamp|period|yr)(_|$)",
    re.I,
)


@dataclass
class ColumnRoles:
    """Structural roles detected from a dataframe."""

    numeric: list[str] = field(default_factory=list)
    categorical: list[str] = field(default_factory=list)
    time: list[str] = field(default_factory=list)
    all_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChartSpec:
    """Fully resolved chart plan — type, axes, aggregation, sort, group."""

    chart_type: str
    x: Optional[str] = None
    y: Optional[str] = None
    color: Optional[str] = None
    aggregation: Optional[str] = None  # sum | mean | count | median | none
    sort_by: Optional[str] = None
    sort_ascending: bool = True
    group_by: Optional[str] = None
    columns: list[str] = field(default_factory=list)
    requested_type: Optional[str] = None
    redirected: bool = False
    redirect_reason: str = ""
    recommended_type: Optional[str] = None
    confidence: float = 1.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def used_columns(self) -> list[str]:
        cols: list[str] = []
        for c in (self.x, self.y, self.color, self.group_by):
            if c and c not in cols:
                cols.append(c)
        for c in self.columns:
            if c and c not in cols:
                cols.append(c)
        return cols


def profile_columns(
    df: pd.DataFrame,
    *,
    time_columns: Sequence[str] | None = None,
) -> ColumnRoles:
    """Classify columns into numeric / categorical / time."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return ColumnRoles()

    all_cols = [str(c) for c in df.columns.tolist()]
    numeric: list[str] = []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            # High-cardinality ints that look like IDs stay numeric for scatter
            numeric.append(str(c))
        else:
            # Try coerce for string years etc.
            coerced = pd.to_numeric(s, errors="coerce")
            if coerced.notna().mean() >= 0.8 and coerced.nunique(dropna=True) > 1:
                numeric.append(str(c))

    # Time: profile hint + dtype + name patterns
    time: list[str] = []
    hinted = [str(c) for c in (time_columns or []) if str(c) in all_cols]
    time.extend(hinted)
    for c in df.columns:
        name = str(c)
        if name in time:
            continue
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            time.append(name)
            continue
        if _TIME_NAME_RE.search(name.replace(" ", "_")):
            # Prefer as time if mostly parseable or numeric year-like
            if name in numeric or pd.api.types.is_numeric_dtype(s):
                time.append(name)
            else:
                parsed = pd.to_datetime(s, errors="coerce", utc=False)
                if parsed.notna().mean() >= 0.7:
                    time.append(name)

    # Categorical = non-numeric excluding pure time-only object columns that are dates
    categorical: list[str] = []
    for c in all_cols:
        if c in numeric:
            continue
        # low-cardinality numeric can also act as category later; skip here
        categorical.append(c)

    # Drop time-only datetime columns from categorical if datetime
    categorical = [
        c
        for c in categorical
        if not (
            c in time
            and c in df.columns
            and pd.api.types.is_datetime64_any_dtype(df[c])
        )
    ]

    return ColumnRoles(
        numeric=numeric,
        categorical=categorical,
        time=list(dict.fromkeys(time)),
        all_columns=all_cols,
    )


def detect_requested_chart_type(question: str) -> Optional[str]:
    """Parse an explicit chart-type request from natural language."""
    q = (question or "").lower()
    if not q:
        return None

    # Order matters — more specific first
    if any(k in q for k in ("heatmap", "correlation matrix", "corr matrix")):
        return "heatmap"
    if "correlation" in q and "scatter" not in q:
        return "heatmap"
    if any(k in q for k in ("scatter", " versus ", " vs ", " vs.", "against ")):
        # "scatter of year versus GDP" / "x vs y"
        return "scatter"
    if re.search(r"\bvs\b", q):
        return "scatter"
    if any(k in q for k in ("histogram", "distribution", "density")):
        return "histogram"
    if any(k in q for k in ("pie chart", "pie ", "donut")):
        return "pie"
    if any(k in q for k in ("line chart", "line graph", "trend", "over time", "time series")):
        return "line"
    if any(k in q for k in ("box plot", "boxplot", "box chart")):
        return "box"
    if any(k in q for k in ("bar chart", "bar graph", "column chart", "by department", "by category")):
        return "bar"
    if "bar" in q and "chart" in q:
        return "bar"
    if "line" in q and "chart" in q:
        return "line"
    if "pie" in q:
        return "pie"
    if "heatmap" in q:
        return "heatmap"
    return None


def _match_column(text: str, columns: Sequence[str]) -> Optional[str]:
    if not text or not columns:
        return None
    t = text.strip().lower()
    for c in columns:
        if c.lower() == t:
            return c
    for c in columns:
        if c.lower() in t or t in c.lower():
            return c
    # token overlap
    tokens = set(re.findall(r"[a-z0-9]+", t))
    best, best_score = None, 0
    for c in columns:
        ctoks = set(re.findall(r"[a-z0-9]+", c.lower()))
        score = len(tokens & ctoks)
        if score > best_score:
            best, best_score = c, score
    return best if best_score > 0 else None


def _infer_xy_from_question(
    question: str,
    roles: ColumnRoles,
) -> tuple[Optional[str], Optional[str]]:
    """Try to pull x/y column names from phrases like 'year versus GDP'."""
    q = (question or "").lower()
    x = y = None

    # Patterns: A versus B / A vs B / A against B / scatter of A and B
    m = re.search(
        r"(?:scatter(?:\s+plot)?\s+of\s+)?(.+?)\s+(?:versus|vs\.?|against)\s+(.+?)(?:\s*$|\s+chart|\s+plot)",
        q,
        re.I,
    )
    if m:
        left, right = m.group(1), m.group(2)
        # strip leading "of" / chart words
        left = re.sub(r"^(scatter|plot|chart|of)\s+", "", left.strip())
        right = re.sub(r"\s+(chart|plot)$", "", right.strip())
        pool = roles.all_columns
        x = _match_column(left, pool)
        y = _match_column(right, pool)

    if x is None and y is None:
        # "histogram of temperature" / "bar chart of salary by department"
        m2 = re.search(
            r"(?:histogram|distribution|bar chart|pie chart|line chart)\s+(?:of\s+)?(.+?)(?:\s+by\s+|\s*$)",
            q,
            re.I,
        )
        if m2:
            y = _match_column(m2.group(1), roles.all_columns)

    m3 = re.search(r"\bby\s+([a-z0-9_ ]+?)(?:\s*$|\s+chart|\s+plot)", q, re.I)
    group = _match_column(m3.group(1), roles.all_columns) if m3 else None
    if group and x is None:
        x = group

    return x, y


def _default_aggregation(chart_type: str, roles: ColumnRoles) -> Optional[str]:
    if chart_type in {"bar", "pie"}:
        return "sum" if roles.numeric else "count"
    if chart_type == "line":
        return "mean"
    if chart_type == "box":
        return None
    return None


def infer_chart_spec(
    df: pd.DataFrame,
    question: str = "",
    *,
    time_columns: Sequence[str] | None = None,
    preferred_type: str | None = None,
    last_columns: Sequence[str] | None = None,
) -> ChartSpec:
    """
    Infer the best chart type and axes for the dataframe + question.

    Does not hard-fail on invalid requests — marks redirect metadata for
    the validator / builder to apply recommendations.
    """
    roles = profile_columns(df, time_columns=time_columns)
    requested = preferred_type or detect_requested_chart_type(question)
    q_x, q_y = _infer_xy_from_question(question, roles)

    # Prefer last-used columns when present
    last = [str(c) for c in (last_columns or []) if str(c) in roles.all_columns]

    notes: list[str] = []

    if not roles.all_columns:
        return ChartSpec(
            chart_type="visualization",
            requested_type=requested,
            confidence=0.0,
            notes=["empty_dataframe"],
        )

    # ── Explicit request path ────────────────────────────────────────────
    if requested == "scatter":
        return _spec_scatter(roles, q_x, q_y, last, notes, requested)
    if requested == "line":
        return _spec_line(roles, q_x, q_y, last, notes, requested)
    if requested == "histogram":
        return _spec_histogram(roles, q_x, q_y, last, notes, requested)
    if requested == "pie":
        return _spec_pie(roles, q_x, q_y, last, notes, requested)
    if requested == "heatmap":
        return _spec_heatmap(roles, notes, requested)
    if requested == "bar":
        return _spec_bar(roles, q_x, q_y, last, notes, requested)
    if requested == "box":
        return _spec_box(roles, q_x, q_y, last, notes, requested)

    # ── Automatic selection ──────────────────────────────────────────────
    return _auto_select(roles, q_x, q_y, last, notes, question)


def _auto_select(
    roles: ColumnRoles,
    q_x: Optional[str],
    q_y: Optional[str],
    last: list[str],
    notes: list[str],
    question: str,
) -> ChartSpec:
    q = (question or "").lower()

    # Time series dominate for trend-ish language or when time exists
    if roles.time and roles.numeric:
        return _spec_line(roles, q_x, q_y, last, notes, None)

    if len(roles.numeric) >= 2 and any(k in q for k in ("correlat", "relationship", "compare")):
        return _spec_heatmap(roles, notes, None)

    if roles.categorical and roles.numeric:
        return _spec_bar(roles, q_x, q_y, last, notes, None)

    if len(roles.numeric) >= 2:
        return _spec_scatter(roles, q_x, q_y, last, notes, None)

    if roles.numeric:
        return _spec_histogram(roles, q_x, q_y, last, notes, None)

    if roles.categorical:
        return _spec_pie(roles, q_x, q_y, last, notes, None)

    notes.append("no_suitable_columns")
    return ChartSpec(chart_type="visualization", confidence=0.0, notes=notes)


def _first_numeric(roles: ColumnRoles, *candidates: Optional[str]) -> Optional[str]:
    for c in candidates:
        if c and c in roles.numeric:
            return c
    return roles.numeric[0] if roles.numeric else None


def _first_categorical(roles: ColumnRoles, *candidates: Optional[str]) -> Optional[str]:
    for c in candidates:
        if c and c in roles.categorical:
            return c
    return roles.categorical[0] if roles.categorical else None


def _first_time(roles: ColumnRoles, *candidates: Optional[str]) -> Optional[str]:
    for c in candidates:
        if c and c in roles.time:
            return c
        # numeric year-like allowed
        if c and c in roles.numeric and _TIME_NAME_RE.search(c.replace(" ", "_")):
            return c
    if roles.time:
        return roles.time[0]
    for c in roles.numeric:
        if _TIME_NAME_RE.search(c.replace(" ", "_")):
            return c
    return None


def _spec_scatter(
    roles: ColumnRoles,
    q_x: Optional[str],
    q_y: Optional[str],
    last: list[str],
    notes: list[str],
    requested: Optional[str],
) -> ChartSpec:
    """Scatter requires two numeric columns. Cat+num → redirect to bar."""
    num = roles.numeric
    cat = roles.categorical

    x_cand = q_x or (last[0] if last else None)
    y_cand = q_y or (last[1] if len(last) > 1 else None)

    x_num = x_cand if x_cand in num else None
    y_num = y_cand if y_cand in num else None
    x_cat = x_cand if x_cand in cat else None
    y_cat = y_cand if y_cand in cat else None

    # Invalid: categorical involved in scatter request
    if requested == "scatter" and (x_cat or y_cat or (x_cand and x_cand not in num) or (y_cand and y_cand not in num)):
        # Country + GDP style → bar
        if (x_cat or y_cat or x_cand in cat or y_cand in cat) and num:
            cat_col = x_cat or y_cat or _first_categorical(roles, x_cand, y_cand)
            val_col = x_num or y_num or _first_numeric(roles, y_cand, x_cand)
            notes.append("scatter_requires_numeric_numeric")
            return ChartSpec(
                chart_type="bar",
                x=cat_col,
                y=val_col,
                aggregation="sum" if val_col else "count",
                sort_by=val_col,
                sort_ascending=False,
                group_by=cat_col,
                columns=[c for c in (cat_col, val_col) if c],
                requested_type=requested,
                redirected=True,
                redirect_reason=(
                    f"Scatter requires two numeric columns; "
                    f"got categorical '{cat_col or x_cand}' with numeric data. "
                    f"Recommended: Bar Chart."
                ),
                recommended_type="bar",
                confidence=0.85,
                notes=notes,
            )

    if len(num) >= 2:
        x = x_num or (num[0] if num[0] != y_num else num[1])
        y = y_num or next((n for n in num if n != x), num[1])
        if x == y and len(num) > 1:
            y = num[1] if num[0] == x else num[0]
        return ChartSpec(
            chart_type="scatter",
            x=x,
            y=y,
            columns=[x, y],
            aggregation=None,
            requested_type=requested,
            confidence=0.9 if requested else 0.75,
            notes=notes,
        )

    if len(num) == 1:
        notes.append("only_one_numeric_column")
        return ChartSpec(
            chart_type="histogram",
            x=num[0],
            columns=[num[0]],
            requested_type=requested,
            redirected=True,
            redirect_reason=(
                "Scatter requires two numeric columns; only one numeric column "
                f"('{num[0]}') is available. Recommended: Histogram."
            ),
            recommended_type="histogram",
            confidence=0.7,
            notes=notes,
        )

    # No numeric — try bar on categorical
    if cat:
        notes.append("no_numeric_for_scatter")
        return ChartSpec(
            chart_type="bar",
            x=cat[0],
            aggregation="count",
            group_by=cat[0],
            columns=[cat[0]],
            requested_type=requested,
            redirected=True,
            redirect_reason="Scatter needs numeric axes; falling back to Bar Chart (counts).",
            recommended_type="bar",
            confidence=0.5,
            notes=notes,
        )

    return ChartSpec(
        chart_type="visualization",
        requested_type=requested,
        redirected=True,
        redirect_reason="Cannot build scatter: no suitable columns.",
        confidence=0.0,
        notes=notes + ["impossible"],
    )


def _spec_line(
    roles: ColumnRoles,
    q_x: Optional[str],
    q_y: Optional[str],
    last: list[str],
    notes: list[str],
    requested: Optional[str],
) -> ChartSpec:
    t = _first_time(roles, q_x, last[0] if last else None)
    y = _first_numeric(roles, q_y, last[1] if len(last) > 1 else None)
    if t and y and t != y:
        return ChartSpec(
            chart_type="line",
            x=t,
            y=y,
            aggregation="mean",
            sort_by=t,
            sort_ascending=True,
            columns=[t, y],
            requested_type=requested,
            confidence=0.92,
            notes=notes,
        )
    if len(roles.numeric) >= 2:
        # Use first numeric as pseudo-x if ordered
        x, y = roles.numeric[0], roles.numeric[1]
        notes.append("line_without_time_using_numeric_x")
        return ChartSpec(
            chart_type="line",
            x=x,
            y=y,
            sort_by=x,
            sort_ascending=True,
            columns=[x, y],
            requested_type=requested,
            confidence=0.6,
            notes=notes,
        )
    if roles.numeric:
        return ChartSpec(
            chart_type="histogram",
            x=roles.numeric[0],
            columns=[roles.numeric[0]],
            requested_type=requested,
            redirected=True,
            redirect_reason="Line chart needs a time/order axis + numeric; using Histogram.",
            recommended_type="histogram",
            confidence=0.55,
            notes=notes,
        )
    return ChartSpec(
        chart_type="visualization",
        requested_type=requested,
        confidence=0.0,
        notes=notes + ["line_impossible"],
    )


def _spec_histogram(
    roles: ColumnRoles,
    q_x: Optional[str],
    q_y: Optional[str],
    last: list[str],
    notes: list[str],
    requested: Optional[str],
) -> ChartSpec:
    col = _first_numeric(roles, q_y, q_x, last[0] if last else None)
    if col:
        return ChartSpec(
            chart_type="histogram",
            x=col,
            columns=[col],
            requested_type=requested,
            confidence=0.9,
            notes=notes,
        )
    if roles.categorical:
        return ChartSpec(
            chart_type="bar",
            x=roles.categorical[0],
            aggregation="count",
            columns=[roles.categorical[0]],
            requested_type=requested,
            redirected=True,
            redirect_reason="Histogram needs a numeric column; using Bar Chart counts.",
            recommended_type="bar",
            confidence=0.6,
            notes=notes,
        )
    return ChartSpec(chart_type="visualization", requested_type=requested, confidence=0.0, notes=notes)


def _spec_pie(
    roles: ColumnRoles,
    q_x: Optional[str],
    q_y: Optional[str],
    last: list[str],
    notes: list[str],
    requested: Optional[str],
) -> ChartSpec:
    cat = _first_categorical(roles, q_x, last[0] if last else None)
    val = _first_numeric(roles, q_y, last[1] if len(last) > 1 else None)
    if cat:
        return ChartSpec(
            chart_type="pie",
            x=cat,
            y=val,
            aggregation="sum" if val else "count",
            group_by=cat,
            columns=[c for c in (cat, val) if c],
            requested_type=requested,
            confidence=0.85,
            notes=notes,
        )
    # Numeric only — bin into pie-like categories via value counts of top buckets
    if roles.numeric:
        notes.append("pie_from_numeric_bins")
        return ChartSpec(
            chart_type="histogram",
            x=roles.numeric[0],
            columns=[roles.numeric[0]],
            requested_type=requested,
            redirected=True,
            redirect_reason=(
                "Pie chart needs a categorical column; only numeric data found. "
                "Recommended: Histogram."
            ),
            recommended_type="histogram",
            confidence=0.55,
            notes=notes,
        )
    return ChartSpec(chart_type="visualization", requested_type=requested, confidence=0.0, notes=notes)


def _spec_heatmap(
    roles: ColumnRoles,
    notes: list[str],
    requested: Optional[str],
) -> ChartSpec:
    if len(roles.numeric) >= 2:
        cols = roles.numeric[:12]  # cap matrix size
        return ChartSpec(
            chart_type="heatmap",
            columns=cols,
            requested_type=requested,
            confidence=0.9,
            notes=notes,
        )
    if len(roles.numeric) == 1:
        return ChartSpec(
            chart_type="histogram",
            x=roles.numeric[0],
            columns=[roles.numeric[0]],
            requested_type=requested,
            redirected=True,
            redirect_reason=(
                "Heatmap needs a numeric matrix (2+ numeric columns). "
                "Recommended: Histogram."
            ),
            recommended_type="histogram",
            confidence=0.55,
            notes=notes + ["heatmap_single_numeric"],
        )
    return ChartSpec(
        chart_type="visualization",
        requested_type=requested,
        redirected=True,
        redirect_reason="Heatmap needs 2+ numeric columns.",
        confidence=0.0,
        notes=notes,
    )


def _spec_bar(
    roles: ColumnRoles,
    q_x: Optional[str],
    q_y: Optional[str],
    last: list[str],
    notes: list[str],
    requested: Optional[str],
) -> ChartSpec:
    cat = _first_categorical(roles, q_x, last[0] if last else None)
    val = _first_numeric(roles, q_y, last[1] if len(last) > 1 else None)
    if cat and val:
        return ChartSpec(
            chart_type="bar",
            x=cat,
            y=val,
            aggregation="sum",
            sort_by=val,
            sort_ascending=False,
            group_by=cat,
            columns=[cat, val],
            requested_type=requested,
            confidence=0.9,
            notes=notes,
        )
    if cat:
        return ChartSpec(
            chart_type="bar",
            x=cat,
            aggregation="count",
            group_by=cat,
            columns=[cat],
            requested_type=requested,
            confidence=0.8,
            notes=notes,
        )
    if val:
        # numeric year + value as bar
        t = _first_time(roles)
        if t and t != val:
            return ChartSpec(
                chart_type="bar",
                x=t,
                y=val,
                aggregation="sum",
                sort_by=t,
                sort_ascending=True,
                columns=[t, val],
                requested_type=requested,
                confidence=0.75,
                notes=notes,
            )
        return ChartSpec(
            chart_type="histogram",
            x=val,
            columns=[val],
            requested_type=requested,
            redirected=True,
            redirect_reason="Bar chart prefers a categorical axis; using Histogram.",
            recommended_type="histogram",
            confidence=0.55,
            notes=notes,
        )
    return ChartSpec(chart_type="visualization", requested_type=requested, confidence=0.0, notes=notes)


def _spec_box(
    roles: ColumnRoles,
    q_x: Optional[str],
    q_y: Optional[str],
    last: list[str],
    notes: list[str],
    requested: Optional[str],
) -> ChartSpec:
    cat = _first_categorical(roles, q_x)
    val = _first_numeric(roles, q_y)
    if cat and val:
        return ChartSpec(
            chart_type="box",
            x=cat,
            y=val,
            group_by=cat,
            columns=[cat, val],
            requested_type=requested,
            confidence=0.88,
            notes=notes,
        )
    if val:
        return ChartSpec(
            chart_type="histogram",
            x=val,
            columns=[val],
            requested_type=requested,
            redirected=True,
            redirect_reason="Box plot needs category + numeric; using Histogram.",
            recommended_type="histogram",
            confidence=0.55,
            notes=notes,
        )
    return _spec_bar(roles, q_x, q_y, last, notes, requested)
