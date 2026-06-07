import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.core.logger import get_logger
from backend.db import get_session, list_sessions, save_session
from backend.graph.workflow import build_graph
from backend.startup.ollama_validator import get_ollama_status, validate_model_inference
from backend.utils.dataset_loader import load_dataset
from backend.utils.json_safe import sanitize_for_json

load_dotenv()

app = FastAPI(title="AI Analyst Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
graph = build_graph()
logger = get_logger(__name__)


@app.on_event("startup")
def validate_ollama():
    try:
        status = get_ollama_status()
        if status["ollama_installed"]:
            logger.info("Ollama installed")
        else:
            logger.warning("Ollama executable not found")

        if status["ollama_running"]:
            logger.info("Ollama running")
        else:
            logger.warning("Ollama server not reachable at %s", settings.OLLAMA_SERVER_URL)

        logger.info("Configured Ollama model: %s", status["model_name"])

        if status["model_available"]:
            logger.info("Model %s available", status["model_name"])
        else:
            logger.warning("Model %s unavailable", status["model_name"])

        if not (status["ollama_installed"] and status["ollama_running"] and status["model_available"]):
            logger.warning("Falling back to rule-based reasoning")
    except Exception as exc:
        logger.warning(
            "Ollama startup validation failed",
            extra={"error": str(exc)},
        )


@app.get("/health/llm")
def health_llm(test_inference: bool = False):
    status = get_ollama_status()
    response = {
        "ollama_installed": status["ollama_installed"],
        "ollama_running": status["ollama_running"],
        "model_available": status["model_available"],
        "configured_model": status["configured_model"],
        "installed_models": status.get("installed_models", []),
    }

    if test_inference:
        try:
            inference_result = validate_model_inference()
            response["inference_success"] = inference_result.get("inference_successful", False)
            if inference_result.get("endpoint") is not None:
                response["endpoint"] = inference_result.get("endpoint")
            if inference_result.get("response_text") is not None:
                response["response_text"] = inference_result.get("response_text")
            if not inference_result.get("inference_successful", False):
                response["error"] = inference_result.get("failure_reason", "Inference failed")
        except Exception as exc:
            logger.warning(
                "Ollama inference health test failed",
                extra={"error": str(exc)},
            )
            response["inference_success"] = False
            response["error"] = str(exc)

    return response


@app.get("/health/full")
def health_full():
    status = get_ollama_status()
    database_status = "ok"
    try:
        get_session("health_check")
    except Exception:
        database_status = "error"

    graph_status = "ok" if graph is not None else "error"

    return {
        "database": database_status,
        "langgraph": graph_status,
        "ollama": {
            "ollama_installed": status["ollama_installed"],
            "ollama_running": status["ollama_running"],
            "model_available": status["model_available"],
            "configured_model": status["configured_model"],
            "installed_models": status.get("installed_models", []),
            "failure_reason": status.get("failure_reason"),
        },
    }


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 3)
    dataset_reference = request.query_params.get("file_path") or request.query_params.get("dataset_path")

    logger.info(
        "HTTP request completed",
        extra={
            "action": "http_request",
            "method": request.method,
            "path": request.url.path,
            "query": dict(request.query_params),
            "dataset": dataset_reference,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


def _load_session_dataset(session):
    if session is None:
        return None

    dataset_path = getattr(session, "dataset_path", None)
    dataset_url = getattr(session, "dataset_url", None)

    if dataset_path:
        try:
            dataset = load_dataset(dataset_path)
            logger.info(
                "Session dataset reloaded",
                extra={"action": "load_session_dataset", "dataset": dataset_path},
            )
            return dataset
        except Exception as exc:
            logger.warning(
                "Failed to load session dataset path",
                extra={"action": "load_session_dataset", "dataset": dataset_path, "error": str(exc)},
            )

    if dataset_url:
        try:
            dataset = load_dataset(dataset_url)
            logger.info(
                "Session dataset reloaded",
                extra={"action": "load_session_dataset", "dataset": dataset_url},
            )
            return dataset
        except Exception as exc:
            logger.warning(
                "Failed to load session dataset URL",
                extra={"action": "load_session_dataset", "dataset": dataset_url, "error": str(exc)},
            )

    return None


def _is_remote_reference(reference: str) -> bool:
    if not reference:
        return False
    parsed = urlparse(reference)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_dataset_reference(file_path: str | None) -> str | None:
    if not file_path:
        return None

    if _is_remote_reference(file_path):
        return file_path

    return str(Path(file_path).expanduser().resolve(strict=False))


def _build_state(session, question=None, file_path=None):
    dataset = None if file_path else _load_session_dataset(session)

    return {
        "data": dataset,
        "last_dataset": dataset,
        "last_column_used": getattr(session, "last_column", None),
        "last_columns_used": getattr(session, "last_columns", None) or [],
        "last_chart_type": getattr(session, "last_chart_type", None),
        "last_intent": getattr(session, "last_intent", None),
        "last_operation": getattr(session, "last_operation", None),
        "last_forecast_target": getattr(session, "last_forecast_target", None),
        "cleaned": False,
        "insights": [],
        "question": question,
        "answer": None,
        "chart": None,
        "charts": [],
        "forecast": [],
        "forecast_chart": None,
        "forecast_error": None,
        "chart_error": None,
        "error_type": None,
        "chart_explanation": None,
        "hypotheses": [],
        "related_datasets": [],
        "last_forecast_target": None,
        "plan": [],
        "dataset_profile": {},
        "dataset_explanation": [],
        "recommended_next_steps": [],
        "detected_patterns": [],
        "dataset_topic": None,
        "chart_columns_used": [],
        "rows": int(dataset.shape[0]) if dataset is not None else 0,
        "columns": dataset.columns.tolist() if dataset is not None else [],
        "error": None,
    }


def _stable_response(result, question=None):
    dataset_profile = result.get("dataset_profile") or {}
    charts = result.get("charts") or []
    if not charts and result.get("chart") is not None:
        charts = [result.get("chart")]

    payload = {
        "question": question or "",
        "answer": result.get("answer") or "",
        "dataset_summary": dataset_profile,
        "dataset_topic": result.get("dataset_topic") or "",
        "charts": charts,
        "generated_charts": charts,
        "chart": result.get("chart") or {},
        "chart_columns_used": result.get("chart_columns_used") or [],
        "forecast": result.get("forecast") or [],
        "forecast_chart": result.get("forecast_chart") or {},
        "forecast_error": result.get("forecast_error") or "",
        "chart_error": result.get("chart_error") or "",
        "detected_patterns": result.get("detected_patterns") or [],
        "insights": result.get("insights") or [],
        "recommended_next_steps": result.get("recommended_next_steps") or [],
        "dataset_explanation": result.get("dataset_explanation") or [],
        "related_datasets": result.get("related_datasets") or [],
        "chart_explanation": result.get("chart_explanation") or "",
        "hypotheses": result.get("hypotheses") or [],
        "dataset_url": result.get("dataset_url") or "",
        "rows": result.get("rows") or 0,
        "columns": result.get("columns") or [],
        "error": result.get("error") or "",
        "error_type": result.get("error_type") or "",
    }
    return sanitize_for_json(payload)


@app.get("/")
def home():
    return {"message": "AI Analyst Backend Running"}


@app.post("/upload")
def upload_dataset(file: UploadFile = File(...)):
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    filename = Path(file.filename or "").name
    if not filename:
        return JSONResponse(
            status_code=400,
            content={"error": "A valid filename is required."},
        )

    upload_path = settings.DATA_DIR / filename

    try:
        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return sanitize_for_json(
            {
                "message": "Dataset uploaded successfully",
                "file_path": str(upload_path),
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": f"Upload failed: {exc}"},
        )


@app.get("/analyze")
def analyze(session_id: str = "default"):
    session = get_session(session_id)
    state = _build_state(session=session, question="analyze dataset")

    try:
        result = graph.invoke(state)

        if result.get("data") is None:
            return JSONResponse(
                status_code=400,
                content=sanitize_for_json(
                    {
                        "error": result.get("answer") or "No dataset available for analysis",
                        "insights": result.get("insights") or [],
                    }
                ),
            )

        save_session(
            session_id=session_id,
            last_column=result.get("last_column_used"),
            last_columns=result.get("last_columns_used") or [],
            last_chart_type=result.get("last_chart_type"),
            last_intent=result.get("last_intent"),
            last_operation=result.get("last_operation"),
            dataset_topic=result.get("dataset_topic"),
        )

        return _stable_response(result)
    except Exception as exc:
        logger.error(
            "Analysis pipeline failed",
            extra={"action": "analyze", "error": str(exc)},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Analysis pipeline failed",
                "details": str(exc),
            },
        )


@app.get("/v1/ask")
@app.get("/ask")
def ask(
    question: str,
    session_id: str = "default",
    file_path: str | None = None,
):
    session = get_session(session_id)
    normalized_file_path = _normalize_dataset_reference(file_path)
    state = _build_state(
        session=session,
        question=question,
        file_path=normalized_file_path,
    )

    if normalized_file_path:
        state["file_path"] = normalized_file_path

    try:
        result = graph.invoke(state)

        save_kwargs = {
            "last_column": result.get("last_column_used"),
            "last_columns": result.get("last_columns_used") or [],
            "last_chart_type": result.get("last_chart_type"),
            "last_intent": result.get("last_intent"),
            "last_operation": result.get("last_operation"),
            "last_forecast_target": result.get("last_forecast_target"),
            "last_query": question,
            "last_insight": result.get("answer"),
            "eda_summary": result.get("dataset_profile") or {},
            "dataset_topic": result.get("dataset_topic"),
        }

        if normalized_file_path and result.get("data") is not None:
            if _is_remote_reference(normalized_file_path):
                save_kwargs["dataset_path"] = None
                save_kwargs["dataset_url"] = normalized_file_path
            elif not result.get("dataset_url"):
                save_kwargs["dataset_path"] = normalized_file_path
                save_kwargs["dataset_url"] = None
        elif result.get("dataset_url") and result.get("data") is not None:
            save_kwargs["dataset_path"] = None
            save_kwargs["dataset_url"] = result["dataset_url"]

        save_session(session_id=session_id, **save_kwargs)

        return _stable_response(result, question=question)
    except Exception as exc:
        logger.error(
            "Ask pipeline failed",
            extra={"action": "ask", "question": question, "error": str(exc)},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Pipeline execution failed",
                "details": str(exc),
            },
        )


@app.get("/sessions")
def sessions():
    try:
        return list_sessions()
    except Exception as exc:
        logger.error(
            "Failed to load session list",
            extra={"action": "sessions", "error": str(exc)},
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Unable to retrieve sessions"},
        )
