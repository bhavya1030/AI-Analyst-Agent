import pandas as pd
from itertools import combinations


def _safe_numeric_series(series):
    return pd.to_numeric(series, errors="coerce").dropna()


def pattern_detection_agent(state):
    df = state.get("data")
    if df is None:
        state["detected_patterns"] = []
        return state

    profile = state.get("dataset_profile", {})
    findings = []
    numeric_cols = profile.get("numeric_columns", [])
    time_columns = profile.get("time_columns", [])
    missing = profile.get("missing_values", {})

    total_rows = max(1, int(df.shape[0]))

    for col, miss_count in missing.items():
        fraction = miss_count / total_rows
        if fraction >= 0.1:
            findings.append(
                f"Missing values cluster detected in '{col}' ({round(fraction * 100, 1)}% missing)."
            )

    if time_columns and numeric_cols:
        time_col = time_columns[0]
        time_series = _safe_numeric_series(df[time_col])
        for col in numeric_cols:
            if col == time_col:
                continue
            y = _safe_numeric_series(df[col])
            joint = pd.concat([time_series, y], axis=1, join="inner").dropna()
            if len(joint) >= 3:
                corr = joint.iloc[:, 0].corr(joint.iloc[:, 1])
                if corr is not None and corr > 0.8:
                    findings.append(
                        f"Strong upward trend detected in '{col}' over '{time_col}'."
                    )
                elif corr is not None and corr < -0.8:
                    findings.append(
                        f"Strong downward trend detected in '{col}' over '{time_col}'."
                    )

    if len(numeric_cols) >= 2:
        corr = df[numeric_cols].corr()
        for a, b in combinations(numeric_cols, 2):
            if pd.isna(corr.loc[a, b]):
                continue
            if abs(corr.loc[a, b]) >= 0.85:
                findings.append(
                    f"High correlation detected between '{a}' and '{b}' ({round(corr.loc[a, b], 2)})."
                )

        for col in numeric_cols:
            series = _safe_numeric_series(df[col])
            if series.empty:
                continue
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                outliers = series[(series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)]
                if len(outliers) >= max(1, 0.01 * len(series)):
                    findings.append(
                        f"Outliers detected in '{col}' with {len(outliers)} extreme values."
                    )

            skewness = series.skew()
            if abs(skewness) >= 1.0:
                direction = "positive" if skewness > 0 else "negative"
                findings.append(
                    f"Skewed distribution detected in '{col}' ({direction} skew)."
                )

    state["detected_patterns"] = findings
    return state
