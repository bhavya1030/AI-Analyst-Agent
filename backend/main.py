from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import shutil
import os

from backend.graph.workflow import build_graph

app = FastAPI(title="AI Analyst Agent API")

# Initialize LangGraph workflow
graph = build_graph()


# -------------------------------
# GLOBAL MEMORY STORAGE
# -------------------------------

LAST_DATASET = None
LAST_COLUMN = None
LAST_COLUMNS = None


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
def analyze():

    global LAST_DATASET

    state = {
        "data": LAST_DATASET,
        "last_dataset": LAST_DATASET,
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

        LAST_DATASET = df

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
def ask(question: str, file_path: str | None = None):

    global LAST_DATASET
    global LAST_COLUMN
    global LAST_COLUMNS

    state = {
        "data": LAST_DATASET,
        "last_dataset": LAST_DATASET,
        "last_column_used": LAST_COLUMN,
        "last_columns_used": LAST_COLUMNS,
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

        # -------------------------------
        # Persist dataset memory
        # -------------------------------

        if result.get("data") is not None:
            LAST_DATASET = result["data"]

        # -------------------------------
        # Persist single-column memory
        # -------------------------------

        if result.get("last_column_used") is not None:
            LAST_COLUMN = result["last_column_used"]

        # -------------------------------
        # Persist multi-column memory
        # -------------------------------

        if result.get("last_columns_used") is not None:
            LAST_COLUMNS = result["last_columns_used"]

        return {
            "question": question,
            "answer": result.get("answer"),
            "insights": result.get("insights"),
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