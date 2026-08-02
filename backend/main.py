"""AI Analyst Agent — FastAPI application entry point.

Phase 3: main.py is now a thin registration layer only.
All business logic lives in:
  backend/orchestrator/  — request_orchestrator, state_builder, response_builder
  backend/api/           — ask, analyze, upload, health, misc
"""

import time

from dotenv import load_dotenv
from fastapi import Request
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.analyze import router as analyze_router
from backend.api.ask import router as ask_router
from backend.api.health import router as health_router
from backend.api.misc import router as misc_router
from backend.api.upload import router as upload_router
from backend.auth.service import ensure_auth_schema
from backend.core.logger import get_logger
from backend.sessions.router import router as sessions_router
from backend.startup.ollama_validator import get_ollama_status

load_dotenv()

app = FastAPI(title="AI Analyst Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from backend.production.profiling_middleware import PipelineProfilingMiddleware

    app.add_middleware(PipelineProfilingMiddleware)
except Exception:
    # Middleware is optional; ask-path timing still works without it
    pass

# --- Router registration ---
app.include_router(sessions_router)
app.include_router(ask_router)
app.include_router(analyze_router)
app.include_router(upload_router)
app.include_router(health_router)
app.include_router(misc_router)

try:
    from backend.production.observability_router import router as observability_router

    app.include_router(observability_router)
except Exception:
    pass

logger = get_logger(__name__)

try:
    ensure_auth_schema()
except Exception as _auth_exc:
    logger.warning("Auth schema init deferred", extra={"error": str(_auth_exc)})


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 3)
    dataset_reference = (
        request.query_params.get("file_path")
        or request.query_params.get("dataset_path")
    )
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
            logger.warning(
                "Ollama server not reachable at %s",
                status.get("ollama_url", "configured URL"),
            )

        logger.info("Configured Ollama model: %s", status["model_name"])

        if status["model_available"]:
            logger.info("Model %s available", status["model_name"])
        else:
            logger.warning("Model %s unavailable", status["model_name"])

        if not (
            status["ollama_installed"]
            and status["ollama_running"]
            and status["model_available"]
        ):
            logger.warning("Falling back to rule-based reasoning")
    except Exception as exc:
        logger.warning(
            "Ollama startup validation failed",
            extra={"error": str(exc)},
        )
