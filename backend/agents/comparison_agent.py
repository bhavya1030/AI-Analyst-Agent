import pandas as pd
import plotly.express as px

from backend.utils.dataset_loader import load_dataset
from backend.utils.json_safe import figure_to_json


DATASET_SOURCES = {
    "gdp": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
    "population": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
    "inflation": "https://raw.githubusercontent.com/datasets/inflation/master/data/cpi.csv"
}


def detect_requested_datasets(question):

    question = question.lower()

    selected = []

    for keyword in DATASET_SOURCES:

        if keyword in question:
            selected.append(keyword)

    return selected


def comparison_agent(state):
    try:
        question = (state.get("question") or "").lower()

        datasets = detect_requested_datasets(question)

        if len(datasets) < 2:

            state["answer"] = "Please specify at least two datasets to compare."
            return state

        dfs = {}

        for name in datasets:

            url = DATASET_SOURCES[name]

            try:

                df = load_dataset(url)

                year_column = next(
                    (col for col in df.columns if col.lower() == "year"),
                    None,
                )

                if year_column is None:
                    continue

                df = df.groupby(year_column).mean(numeric_only=True).reset_index()
                df = df.rename(columns={year_column: "year"})

                if "value" not in [col.lower() for col in df.columns]:
                    numeric_cols = [
                        col for col in df.columns
                        if col.lower() != "year"
                        and pd.api.types.is_numeric_dtype(df[col])
                    ]
                    if not numeric_cols:
                        continue
                    df = df.rename(columns={numeric_cols[0]: name})
                else:
                    value_col = next(
                        col for col in df.columns if col.lower() == "value"
                    )
                    df = df.rename(columns={value_col: name})

                dfs[name] = df

            except Exception:

                continue

        if len(dfs) < 2:

            state["answer"] = "Could not load enough datasets for comparison."
            return state

        merged = None

        for _, df in dfs.items():
            if merged is None:
                merged = df
            else:
                merged = pd.merge(merged, df, on="year", how="inner")

        if merged is None or merged.empty:
            state["answer"] = "Comparison failed because the datasets do not share overlapping years."
            state["chart"] = None
            return state

        numeric_cols = [col for col in merged.columns if col != "year"]

        if len(numeric_cols) < 2:

            state["answer"] = "Comparison failed due to missing numeric overlap."
            return state

        x = numeric_cols[0]
        y = numeric_cols[1]

        corr = merged[x].corr(merged[y])

        fig = px.scatter(merged, x=x, y=y)

        state["chart"] = figure_to_json(fig)
        state["chart_columns_used"] = [x, y]
        state["rows"] = int(merged.shape[0])
        state["columns"] = merged.columns.tolist()

        if pd.isna(corr):
            state["answer"] = f"Comparison chart created for {x} and {y}, but correlation could not be computed."
        else:
            state["answer"] = f"Correlation between {x} and {y} is {round(corr, 3)}"

        return state
    except Exception as exc:
        state["chart"] = None
        state["chart_columns_used"] = []
        state["answer"] = "Comparison failed."
        state["error"] = f"Comparison failed: {exc}"
        return state
