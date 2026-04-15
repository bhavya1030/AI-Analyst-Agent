import numpy as np
import pandas as pd


def _format_trend(slope):
    if slope > 0.01:
        return "increasing"
    if slope < -0.01:
        return "decreasing"
    return "relatively stable"


def _describe_correlation(df, cols):
    if len(cols) < 2:
        return None
    corr = df[cols].corr().iloc[0, 1]
    if pd.isna(corr):
        return None
    if abs(corr) >= 0.75:
        strength = "strong"
    elif abs(corr) >= 0.4:
        strength = "moderate"
    else:
        strength = "weak"
    direction = "positive" if corr > 0 else "negative"
    return f"The chart shows a {strength} {direction} correlation between {cols[0]} and {cols[1]}."


def _detect_outliers(series):
    if series.empty:
        return None
    z_scores = np.abs((series - series.mean()) / series.std(ddof=0))
    outliers = (z_scores > 3).sum()
    if outliers > 0:
        return f"There are {int(outliers)} outlier points visible."
    return None


def _describe_skew(series):
    if series.empty:
        return None
    skewness = series.skew()
    if np.isnan(skewness):
        return None
    if skewness > 1:
        return "The distribution is strongly right-skewed."
    if skewness > 0.5:
        return "The distribution is moderately right-skewed."
    if skewness < -1:
        return "The distribution is strongly left-skewed."
    if skewness < -0.5:
        return "The distribution is moderately left-skewed."
    return "The distribution is approximately symmetric."


def _create_forecast_explanation(forecast):
    if not forecast:
        return None
    try:
        yhat = np.array([float(row.get("yhat", np.nan)) for row in forecast])
        lower = np.array([float(row.get("yhat_lower", np.nan)) for row in forecast])
        upper = np.array([float(row.get("yhat_upper", np.nan)) for row in forecast])
        if yhat.size == 0 or np.isnan(yhat).all():
            return None
        slope = np.nan
        x_vals = np.arange(len(yhat))
        valid = ~np.isnan(yhat)
        if valid.sum() >= 2:
            slope = np.polyfit(x_vals[valid], yhat[valid], 1)[0]
        width = np.nanmean(upper - lower)
        confidence = "narrow" if width / np.nanmean(np.abs(yhat) + 1e-9) < 0.1 else "wide"
        direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable"
        return f"Forecast confidence intervals are {confidence}, and predicted values are {direction}."
    except Exception:
        return None


def chart_interpretation_agent(state):
    df = state.get("data")
    if df is None:
        state["chart_explanation"] = None
        return state

    chart_type = state.get("last_chart_type")
    cols = state.get("chart_columns_used") or []
    explanation_parts = []

    if chart_type == "line" and len(cols) >= 2:
        time_col, value_col = cols[0], cols[1]
        if value_col in df and time_col in df:
            series = pd.to_numeric(df[value_col], errors="coerce").dropna()
            if len(series) >= 2:
                slope = np.polyfit(np.arange(len(series)), series.values, 1)[0]
                explanation_parts.append(
                    f"The line chart for {value_col} shows a { _format_trend(slope)} trend over time."
                )
            outlier = _detect_outliers(series)
            if outlier:
                explanation_parts.append(outlier)

    if chart_type == "scatter" and len(cols) >= 2:
        explanation = _describe_correlation(df, cols[:2])
        if explanation:
            explanation_parts.append(explanation)
        outlier = _detect_outliers(df[cols[1]].dropna())
        if outlier:
            explanation_parts.append(outlier)

    if chart_type == "heatmap" and len(cols) >= 2:
        explanation = _describe_correlation(df, cols[:2])
        if explanation:
            explanation_parts.append(explanation)
        explanation_parts.append(
            "The heatmap highlights correlation strengths between numeric features."
        )

    if chart_type in {"box", "histogram", "distribution"} and cols:
        series = pd.to_numeric(df[cols[-1]], errors="coerce").dropna()
        skew_desc = _describe_skew(series)
        if skew_desc:
            explanation_parts.append(skew_desc)
        outlier = _detect_outliers(series)
        if outlier:
            explanation_parts.append(outlier)

    if state.get("forecast"):
        forecast_explanation = _create_forecast_explanation(state.get("forecast"))
        if forecast_explanation:
            explanation_parts.append(forecast_explanation)

    if not explanation_parts:
        explanation_parts.append("The chart shows data trends and relationships worth reviewing.")

    state["chart_explanation"] = " ".join(explanation_parts)
    return state
