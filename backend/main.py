from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from backend.graph.workflow import build_graph

from fastapi import UploadFile, File
import shutil
import os

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
def ask(question: str, file_path: str = "data/sample.csv"):

    state = {
        "data": None,
        "cleaned": False,
        "insights": [],
        "question": question,
        "answer": None,
        "chart": None,
        "plan": [],
        "file_path": file_path,
    }

    result = graph.invoke(state)

    return {
        "question": question,
        "answer": result.get("answer"),
        "chart": result.get("chart"),
        "insights": result.get("insights"),
    }

@app.post("/upload")
def upload_dataset(file: UploadFile = File(...)):

    upload_path = f"data/{file.filename}"

    with open(upload_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "message": "Dataset uploaded successfully",
        "file_path": upload_path
    }