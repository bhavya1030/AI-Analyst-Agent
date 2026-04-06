import plotly.express as px


def viz_agent(state):
    df = state["data"]
    question = state["question"].lower()

    fig = None

    if "distribution" in question and "salary" in question:
        fig = px.histogram(df, x="salary")

    elif "scatter" in question and "age" in question:
        fig = px.scatter(df, x="age", y="salary")

    elif "bar" in question:
        fig = px.bar(df, x=df.columns[0], y=df.columns[2])

    state["chart"] = fig.to_json() if fig else None

    return state