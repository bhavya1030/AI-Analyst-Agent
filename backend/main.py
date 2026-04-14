from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import shutil
import os
import pandas as pd

from backend.graph.workflow import build_graph
from backend.db import get_session, save_session

app = FastAPI(title="AI Analyst Agent API")

# Initialize LangGraph workflow
graph = build_graph()


# -------------------------------
# Root Endpoint
# -------------------------------

@app.get("/")
def home():
    return {"message": "AI Analyst Backend Running 🚀"}


# -------------------------------
# Dataset Upload Endpoint
# -------------------------------

@app.post("/upload")
def upload_dataset(file: UploadFile = File(...)):

    os.makedirs("data", exist_ok=True)

    upload_path = f"data/{file.filename}"

    try:

        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "message": "Dataset uploaded successfully",
            "file_path": upload_path
        }

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={"error": f"Upload failed: {str(e)}"}
        )


# -------------------------------
# Automated Analysis Endpoint
# -------------------------------

@app.get("/analyze")
def analyze(session_id: str = "default"):

    session = get_session(session_id)

    dataset = None

    if session and session.dataset_path:
        try:
            dataset = pd.read_csv(session.dataset_path)
            print("SESSION DATASET RELOADED:", session.dataset_path)
        except Exception as e:
            print("FAILED TO LOAD SESSION DATASET:", e)

    state = {
        "data": dataset,
        "last_dataset": dataset,
        "last_column_used": session.last_column if session else None,
        "last_columns_used": session.last_columns if session else None,
        "cleaned": False,
        "insights": [],
        "question": None,
        "answer": None,
        "chart": None,
        "plan": []
    }

    try:

        result = graph.invoke(state)

        df = result.get("data")

        if df is None:
            return JSONResponse(
                status_code=400,
                content={"error": "No dataset available for analysis"}
            )

        return {
            "rows": len(df),
            "columns": list(df.columns),
            "insights": result.get("insights")
        }

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={
                "error": "Analysis pipeline failed",
                "details": str(e)
            }
        )


# -------------------------------
# Main AI Analyst Query Endpoint
# -------------------------------

@app.get("/ask")
def ask(
    question: str,
    session_id: str = "default",
    file_path: str | None = None
):

    session = get_session(session_id)

    dataset = None

    if session and session.dataset_path:
        try:
            dataset = pd.read_csv(session.dataset_path)
            print("SESSION DATASET RELOADED:", session.dataset_path)
        except Exception as e:
            print("FAILED TO LOAD SESSION DATASET:", e)

    state = {
        "data": dataset,
        "last_dataset": dataset,
        "last_column_used": session.last_column if session else None,
        "last_columns_used": session.last_columns if session else None,
        "cleaned": False,
        "insights": [],
        "question": question,
        "answer": None,
        "chart": None,
        "plan": []
    }

    if file_path:
        state["file_path"] = file_path

    try:

        result = graph.invoke(state)

        dataset_path = None

        if file_path:
            dataset_path = file_path

        elif result.get("dataset_url"):
            dataset_path = result["dataset_url"]

        save_session(
            session_id=session_id,
            dataset_path=dataset_path,
            last_column=result.get("last_column_used"),
            last_columns=result.get("last_columns_used"),
        )

        return {
            "question": question,
            "answer": result.get("answer"),
            "insights": result.get("insights"),
            "dataset_profile": result.get("dataset_profile"),
            "recommended_next_steps": result.get("recommended_next_steps", []),
            "chart": result.get("chart"),
            "dataset_url": result.get("dataset_url"),
            "dataset_topic": result.get("dataset_topic"),
            "rows": result.get("rows"),
            "columns": result.get("columns"),
            "chart_columns_used": result.get("chart_columns_used"),
            "error": result.get("error"),
        }

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={
                "error": "Pipeline execution failed",
                "details": str(e)
            }
        )