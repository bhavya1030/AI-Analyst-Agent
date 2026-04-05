from fastapi import FastAPI
from backend.graph.workflow import build_graph

app = FastAPI()

graph = build_graph()


@app.get("/")
def home():
    return {"message": "AI Analyst Backend Running 🚀"}


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
    }

    result = graph.invoke(state)

    return {
        "question": question,
        "answer": result["answer"]
    }