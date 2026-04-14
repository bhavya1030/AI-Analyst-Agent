import pandas as pd
import plotly.express as px


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

    question = state.get("question", "").lower()

    datasets = detect_requested_datasets(question)

    if len(datasets) < 2:

        state["answer"] = "Please specify at least two datasets to compare."
        return state

    dfs = {}

    for name in datasets:

        url = DATASET_SOURCES[name]

        try:

            df = pd.read_csv(url)

            if "Year" not in df.columns:
                continue

            df = df.groupby("Year").mean(numeric_only=True).reset_index()

            dfs[name] = df

        except Exception:

            continue

    if len(dfs) < 2:

        state["answer"] = "Could not load enough datasets for comparison."
        return state

    merged = None

    for name, df in dfs.items():

        df = df.rename(columns={"Value": name})

        if merged is None:
            merged = df

        else:
            merged = pd.merge(merged, df, on="Year", how="inner")

    numeric_cols = [col for col in merged.columns if col != "Year"]

    if len(numeric_cols) < 2:

        state["answer"] = "Comparison failed due to missing numeric overlap."
        return state

    x = numeric_cols[0]
    y = numeric_cols[1]

    corr = merged[x].corr(merged[y])

    fig = px.scatter(merged, x=x, y=y, trendline="ols")

    state["chart"] = fig.to_dict()

    state["answer"] = f"Correlation between {x} and {y} is {round(corr,3)}"

    return state