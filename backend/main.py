from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from backend.graph.workflow import build_graph

app = FastAPI()

graph = build_graph()


@app.get("/")
def home():
    return {"message": "AI Analyst Backend Running 🚀"}

from fastapi.responses import HTMLResponse
import plotly.io as pio


@app.get("/analyze")
def analyze():

    state = {
        "data": None,
        "cleaned": False,
        "insights": [],
        "question": None,
        "answer": None,
    }

    result = graph.invoke(state)

    df = result["data"]
    insights = result["insights"]

    return {
        "rows": len(df),
        "columns": list(df.columns),
        "eda_summary": insights
    }

@app.get("/ask")
def ask(question: str):

    state = {
        "data": None,
        "cleaned": False,
        "insights": [],
        "question": question,
        "answer": None,
        "chart": None,
    }

    result = graph.invoke(state)

    if result.get("chart"):
        fig = pio.from_json(result["chart"])
        return HTMLResponse(fig.to_html(full_html=True))

    return {
        "question": question,
        "answer": result.get("answer"),
    }