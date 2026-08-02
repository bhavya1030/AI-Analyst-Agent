"""Health check routes — /health/full and /health/llm."""

from __future__ import annotations

from fastapi import APIRouter

from backend.core.logger import get_logger
from backend.startup.ollama_validator import get_ollama_status, validate_model_inference

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health/llm")
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
            response["inference_success"] = inference_result.get(
                "inference_successful", False
            )
            if inference_result.get("endpoint") is not None:
                response["endpoint"] = inference_result.get("endpoint")
            if inference_result.get("response_text") is not None:
                response["response_text"] = inference_result.get("response_text")
            if not inference_result.get("inference_successful", False):
                response["error"] = inference_result.get(
                    "failure_reason", "Inference failed"
                )
        except Exception as exc:
            logger.warning(
                "Ollama inference health test failed",
                extra={"error": str(exc)},
            )
            response["inference_success"] = False
            response["error"] = str(exc)

    return response


@router.get("/health/full")
def health_full():
    status = get_ollama_status()
    database_status = "ok"
    try:
        from backend.db import SessionLocal
        from sqlalchemy import text as _text

        with SessionLocal() as _db_check:
            _db_check.execute(_text("SELECT 1"))
    except Exception:
        database_status = "error"

    # Check graph availability through the orchestrator singleton
    try:
        from backend.orchestrator.request_orchestrator import get_orchestrator

        graph_status = "ok" if get_orchestrator()._graph is not None else "error"
    except Exception:
        graph_status = "error"

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
