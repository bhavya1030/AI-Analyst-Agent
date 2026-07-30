import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.auth.context import AuthUser
from backend.auth.deps import get_current_user
from backend.auth.service import ensure_auth_schema
from backend.config import settings
from backend.core.logger import get_logger
from backend.db import get_session, save_session
from backend.graph.checkpoint_service import get_checkpoint_service
from backend.graph.workflow import build_graph
from backend.memory.hierarchy import get_memory_hierarchy
from backend.sessions.router import router as sessions_router
from backend.sessions.service import SessionAccessDenied, get_session_service
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
try:
    from backend.production.profiling_middleware import PipelineProfilingMiddleware

    app.add_middleware(PipelineProfilingMiddleware)
except Exception as _mw_exc:
    # Middleware is optional; ask-path timing still works without it
    pass

app.include_router(sessions_router)
try:
    from backend.production.observability_router import router as observability_router

    app.include_router(observability_router)
except Exception as _obs_exc:
    pass
graph = build_graph()
logger = get_logger(__name__)

try:
    ensure_auth_schema()
except Exception as _auth_exc:
    logger.warning("Auth schema init deferred", extra={"error": str(_auth_exc)})


def _graph_config(session_id: str) -> dict:
    """LangGraph runnable config: thread_id ties checkpoints to the session."""
    return {"configurable": {"thread_id": session_id or "default"}}


def _invoke_graph(state: dict, session_id: str):
    """Invoke graph with session-scoped checkpointing when available."""
    try:
        return graph.invoke(state, _graph_config(session_id))
    except TypeError:
        # Compiled without config support
        return graph.invoke(state)
    except Exception as exc:
        # Fall back to non-checkpointed invoke if checkpointer misbehaves
        msg = str(exc).lower()
        if "thread" in msg or "checkpointer" in msg or "configurable" in msg:
            logger.warning(
                "Checkpointed invoke failed; retrying without config",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return graph.invoke(state)
        raise


def _save_turn_checkpoint(session_id: str, result: dict) -> dict | None:
    try:
        return get_checkpoint_service().save_turn_checkpoint(
            session_id, result, source="turn"
        )
    except Exception as exc:
        logger.warning(
            "Turn checkpoint save failed",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return None


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


def _question_is_new_topic(
    question: str | None,
    active_topic: str | None,
    *,
    has_active_dataset: bool = False,
) -> bool:
    """True when the user named a different subject than the session dataset."""
    from backend.memory.continuity import is_new_dataset_topic

    return is_new_dataset_topic(
        question,
        active_topic,
        has_active_dataset=has_active_dataset,
    )


def _build_state(session, question=None, file_path=None):
    # Session memory: reload the active dataset so follow-ups like
    # "show histogram" / "forecast it" work without re-uploading.
    from backend.memory.continuity import should_reuse_session_dataset

    dataset_url = getattr(session, "dataset_url", None) if session is not None else None
    dataset_path = getattr(session, "dataset_path", None) if session is not None else None
    dataset_topic = getattr(session, "dataset_topic", None) if session is not None else None
    session_topic_for_provider = dataset_topic

    has_binding = bool(dataset_path or dataset_url)
    reuse, topic_mismatch = should_reuse_session_dataset(
        question=question,
        dataset_topic=dataset_topic,
        dataset_path=dataset_path,
        dataset_url=dataset_url,
        has_frame=False,
        file_path_override=file_path,
    )

    # Hard stop: "analyze gold..." must NOT keep India GDP from session memory.
    if topic_mismatch and not file_path:
        dataset = None
        dataset_url = None
        dataset_path = None
        logger.info(
            "Session dataset cleared for new topic",
            extra={
                "action": "build_state",
                "previous_topic": dataset_topic,
                "question": question,
            },
        )
        dataset_topic = None
        reuse = False
    else:
        dataset = None if file_path else _load_session_dataset(session)
        if dataset is not None:
            reuse = True
            topic_mismatch = False

    bound_path = None if file_path else dataset_path
    return {
        "data": dataset,
        "last_dataset": dataset,
        "last_column_used": getattr(session, "last_column", None) if session is not None else None,
        "last_columns_used": (getattr(session, "last_columns", None) or []) if session is not None else [],
        "last_chart_type": getattr(session, "last_chart_type", None) if session is not None else None,
        "last_intent": getattr(session, "last_intent", None) if session is not None else None,
        "last_operation": getattr(session, "last_operation", None) if session is not None else None,
        "last_forecast_target": getattr(session, "last_forecast_target", None) if session is not None else None,
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
        "plan": [],
        "dataset_profile": {},
        "dataset_explanation": [],
        "recommended_next_steps": [],
        "detected_patterns": [],
        "dataset_topic": dataset_topic,
        "dataset_url": dataset_url,
        "dataset_path": bound_path,
        "file_path": file_path or bound_path,
        "local_path": bound_path if bound_path and not str(bound_path).startswith(("http://", "https://")) else None,
        "has_active_dataset": dataset is not None or bool(bound_path or dataset_url),
        "reuse_active_dataset": bool(reuse and not topic_mismatch),
        "topic_mismatch": topic_mismatch,
        "force_reload_dataset": topic_mismatch,
        "planner_skip_upload": bool(reuse and not topic_mismatch),
        "chart_columns_used": [],
        "rows": int(dataset.shape[0]) if dataset is not None else 0,
        "columns": dataset.columns.tolist() if dataset is not None else [],
        "error": None,
        "needs_user_data": False,
        "data_acquisition_options": [],
        "dataset_discovery": {},
        "search_queries": [],
        "source": "session" if dataset is not None and not file_path else None,
        "dataset_source": None,
        "focus_country": None,
        "dataset_id": getattr(session, "dataset_id", None) if session is not None else None,
        "registry_id": None,
        "dataset_metadata": {},
        "retrieval_result": {},
        "acquisition_result": {},
        "dataset_intelligence": {},
        "learning_result": {},
        "session_dataset_topic": session_topic_for_provider,
        "memory": {},
        "conversation_memory": {},
        "session_memory": {},
        "dataset_memory": {},
        "knowledge_memory": {},
        "memory_hierarchy_loaded": False,
        "recent_messages": [],
        "selected_columns": (getattr(session, "last_columns", None) or []) if session is not None else [],
        "filters": [],
    }

def _stable_response(result, question=None, timings=None):
    dataset_profile = result.get("dataset_profile") or {}
    charts = result.get("charts") or []
    if not charts and result.get("chart") is not None:
        charts = [result.get("chart")]

    # Merge stage timings from graph state + request timer
    from backend.production.pipeline_timing import (
        extract_timings_from_state,
        get_timer,
        merge_timings,
    )

    state_timings = extract_timings_from_state(result if isinstance(result, dict) else {})
    timer = get_timer()
    timer_timings = timer.as_dict() if timer is not None else {}
    merged = merge_timings(state_timings, timer_timings, timings if isinstance(timings, dict) else None)
    if "total" not in merged and timer is not None:
        merged["total"] = timer.as_dict().get("total", 0)

    payload = {
        "question": question or "",
        "answer": result.get("answer") or "",
        "dataset_summary": dataset_profile,
        "dataset_topic": result.get("dataset_topic") or result.get("dataset_name") or "",
        "dataset_name": result.get("dataset_name")
        or result.get("dataset_title")
        or (result.get("dataset_metadata") or {}).get("title")
        or result.get("dataset_topic")
        or "",
        "charts": charts,
        "generated_charts": charts,
        "chart": result.get("chart") or {},
        "chart_columns_used": result.get("chart_columns_used") or [],
        "forecast": result.get("forecast") or [],
        "forecast_chart": result.get("forecast_chart") or {},
        "forecast_error": result.get("forecast_error") or "",
        "forecast_model": result.get("forecast_model") or "",
        "forecast_partial": bool(result.get("forecast_partial")),
        "forecast_from_cache": bool(result.get("forecast_from_cache")),
        "forecast_timings": result.get("forecast_timings") or {},
        "forecast_explanation": result.get("forecast_explanation") or "",
        "forecast_suggested_retry": result.get("forecast_suggested_retry") or "",
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
        # Open-world acquisition: open data / upload / connect sources
        "needs_user_data": bool(result.get("needs_user_data")),
        "data_acquisition_options": result.get("data_acquisition_options") or [],
        "dataset_discovery": result.get("dataset_discovery") or {},
        "search_queries": result.get("search_queries") or [],
        "source": result.get("source") or result.get("dataset_source") or "",
        "product_promise": (
            "Ask about any topic. We'll find open data when we can, "
            "use your files when you have them, or connect your sources — "
            "then analyze, chart, and forecast."
        ),
        "dataset_learned": bool(result.get("dataset_learned")),
        "learned_aliases": result.get("learned_aliases") or [],
        "topic_via_llm": bool(result.get("topic_via_llm")),
        "timings": merged,
    }
    return sanitize_for_json(payload)


@app.get("/")
def home():
    return {"message": "AI Analyst Backend Running"}


@app.get("/v1/learned-datasets")
@app.get("/learned-datasets")
def learned_datasets(limit: int = 50):
    """List datasets the copilot has remembered from successful loads."""
    try:
        from backend.memory.learned_datasets import list_learned_datasets

        return sanitize_for_json({"learned_datasets": list_learned_datasets(limit=limit)})
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "Could not list learned datasets", "details": str(exc)},
        )


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
def analyze(
    session_id: str = "default",
    user: AuthUser = Depends(get_current_user),
):
    session_svc = get_session_service()
    memory_svc = get_memory_hierarchy()
    user_id = user.user_id
    try:
        session_svc.ensure_session(session_id, user_id=user_id)
    except SessionAccessDenied:
        return JSONResponse(
            status_code=403,
            content={
                "error": f"Access denied to session '{session_id}'",
                "code": "SESSION_ACCESS_DENIED",
                "user_id": user_id,
            },
        )
    except Exception as exc:
        logger.warning(
            "Session ensure failed on analyze",
            extra={"session_id": session_id, "error": str(exc)},
        )

    session = get_session(session_id)
    state = _build_state(session=session, question="analyze dataset")
    state["session_id"] = session_id
    state["user_id"] = user_id

    # Phase 5: load → inject memory hierarchy before graph
    memory_bundle = None
    try:
        memory_bundle = memory_svc.load(
            session_id,
            user_id=user_id,
            dataset_topic=getattr(session, "dataset_topic", None) if session else None,
            dataset_url=getattr(session, "dataset_url", None) if session else None,
            dataset_path=getattr(session, "dataset_path", None) if session else None,
            question="analyze dataset",
        )
        state = memory_svc.inject_into_state(state, memory_bundle)
    except Exception as mem_exc:
        logger.warning(
            "Memory hierarchy load failed on analyze",
            extra={"session_id": session_id, "error": str(mem_exc)},
        )

    try:
        result = _invoke_graph(state, session_id)

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

        # Phase 1: durable session turn + legacy dual-write
        try:
            session_svc.append_user_message(
                session_id, "analyze dataset", user_id=user_id
            )
            session_svc.record_assistant_turn(
                session_id,
                question="analyze dataset",
                result=result,
                user_id=user_id,
            )
        except Exception as persist_exc:
            logger.warning(
                "Session persistence failed on analyze; falling back to legacy save",
                extra={"session_id": session_id, "error": str(persist_exc)},
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

        # Phase 5: persist updated hierarchy
        try:
            memory_svc.persist(
                session_id,
                result,
                user_id=user_id,
                question="analyze dataset",
                prior=memory_bundle,
            )
        except Exception as mem_exc:
            logger.warning(
                "Memory hierarchy persist failed on analyze",
                extra={"session_id": session_id, "error": str(mem_exc)},
            )

        # Phase 6: durable turn checkpoint (graph + planner, no DataFrames)
        ckpt = _save_turn_checkpoint(session_id, result)
        response = _stable_response(result)
        if isinstance(response, dict):
            response["user_id"] = user_id
            if ckpt:
                response["checkpoint_id"] = ckpt.get("checkpoint_id")
                response["checkpoint_saved"] = True
        return response
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


@app.get("/v1/cache/stats")
@app.get("/cache/stats")
def cache_stats(user: AuthUser = Depends(get_current_user)):
    """Ask-level + durable analysis cache statistics."""
    from backend.cache.ask_cache import get_ask_cache

    try:
        stats = get_ask_cache().stats()
        stats["user_id"] = user.user_id
        return sanitize_for_json(stats)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "Unable to read cache stats", "details": str(exc)},
        )


@app.post("/v1/cache/invalidate")
@app.post("/cache/invalidate")
def cache_invalidate(
    fingerprint: str | None = None,
    file_path: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    """Invalidate cache entries when a dataset changes."""
    from backend.cache.ask_cache import get_ask_cache, resolve_dataset_fingerprint

    fp = (fingerprint or "").strip()
    if not fp and file_path:
        fp = resolve_dataset_fingerprint(file_path=file_path) or ""
    if not fp:
        return JSONResponse(
            status_code=400,
            content={"error": "fingerprint or file_path is required"},
        )
    deleted = get_ask_cache().invalidate_dataset(fp)
    return sanitize_for_json(
        {
            "fingerprint": fp,
            "deleted": deleted,
            "user_id": user.user_id,
            "stats": get_ask_cache().stats(),
        }
    )


@app.get("/v1/metrics/timings")
@app.get("/metrics/timings")
def metrics_timings(user: AuthUser = Depends(get_current_user)):
    """Aggregate stage timing stats across process lifetime."""
    from backend.production.pipeline_timing import aggregate_timing_stats

    return sanitize_for_json(
        {"stages": aggregate_timing_stats(), "user_id": user.user_id}
    )


# Note: GET /metrics, /health, /performance are registered via observability_router


@app.get("/v1/ask")
@app.get("/ask")
def ask(
    question: str,
    session_id: str = "default",
    file_path: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    import time as _time

    from backend.cache.ask_cache import (
        get_ask_cache,
        primary_intent,
        resolve_dataset_fingerprint,
    )
    from backend.cache.fingerprint import compute_dataset_fingerprint
    from backend.production.pipeline_timing import (
        pipeline_timer,
        record_stage_ms,
        time_stage,
    )

    ask_t0 = _time.perf_counter()
    with pipeline_timer(session_id=session_id, question=(question or "")[:120]) as timer:
        session_svc = get_session_service()
        memory_svc = get_memory_hierarchy()
        user_id = user.user_id
        normalized_file_path = _normalize_dataset_reference(file_path)
        ask_cache = get_ask_cache()

        t_intent = _time.perf_counter()
        intent = primary_intent(question)
        record_stage_ms("intent", (_time.perf_counter() - t_intent) * 1000)

        # Phase 1: ensure durable session + append user message before the graph run
        try:
            with time_stage("session"):
                session_svc.ensure_session(session_id, user_id=user_id)
                session_svc.append_user_message(session_id, question, user_id=user_id)
        except SessionAccessDenied:
            return JSONResponse(
                status_code=403,
                content={
                    "error": f"Access denied to session '{session_id}'",
                    "code": "SESSION_ACCESS_DENIED",
                    "user_id": user_id,
                    "timings": timer.as_dict(),
                },
            )
        except Exception as exc:
            logger.warning(
                "Session user-message persist failed; continuing ask",
                extra={"session_id": session_id, "error": str(exc)},
            )

        with time_stage("session"):
            session = get_session(session_id)

        # --- Ask-level cache lookup (skip Planner/EDA/Viz/Forecast on hit) ---
        with time_stage("cache"):
            # Prefer session-stored fingerprint (no file re-hash)
            cache_fp = None
            if session is not None:
                try:
                    from backend.memory.hierarchy_store import load_session_memory_blob

                    blob = load_session_memory_blob(session_id) or {}
                    cache_fp = blob.get("dataset_fingerprint") or None
                except Exception:
                    cache_fp = None
            if not cache_fp:
                cache_fp = resolve_dataset_fingerprint(
                    file_path=normalized_file_path
                    if normalized_file_path and not _is_remote_reference(normalized_file_path)
                    else None,
                    dataset_path=getattr(session, "dataset_path", None) if session else None,
                    dataset_url=getattr(session, "dataset_url", None) if session else None,
                )
            # Skip expensive registry match_topic on warm path — only if still no fp
            # and no session binding (rare cold open-world case without file)

            cached_body, cache_meta = (None, {})
            if cache_fp:
                cached_body, cache_meta = ask_cache.get(
                    cache_fp,
                    question,
                    intent=intent,
                    file_path=normalized_file_path,
                )

        if cached_body:
            # Warm path: Auth ✓ · Session update ✓ · Serialize ✓
            # Do NOT run planner / retrieval / EDA / viz / forecast / insights.
            try:
                with time_stage("session"):
                    turn = session_svc.record_cached_assistant_turn(
                        session_id,
                        question=question,
                        result=cached_body,
                        file_path=normalized_file_path,
                        user_id=user_id,
                    )
            except Exception:
                turn = None
            elapsed_ms = (_time.perf_counter() - ask_t0) * 1000
            lookup_ms = float(cache_meta.get("lookup_ms") or cache_meta.get("cache_latency_ms") or 0)
            cold_ms = cache_meta.get("cold_ms")
            saved_ms = cache_meta.get("saved_time_ms")
            if saved_ms is None and cold_ms is not None:
                try:
                    saved_ms = max(0.0, float(cold_ms) - elapsed_ms)
                except Exception:
                    saved_ms = None

            # Cached body already sanitized at store time — avoid deep re-walk
            ser_t0 = _time.perf_counter()
            response = dict(cached_body)
            response.pop("_cold_ms", None)
            response.pop("_sanitized", None)
            response["question"] = question
            response["session_id"] = session_id
            response["user_id"] = user_id
            response["cache_hit"] = True
            response["cache_skipped_pipeline"] = True
            response["cache_latency_ms"] = round(lookup_ms, 2)
            response["saved_time_ms"] = (
                round(float(saved_ms), 2) if saved_ms is not None else None
            )
            response["response_ms"] = round(elapsed_ms, 2)
            response["cache"] = {
                **cache_meta,
                "cache_hit": True,
                "cache_latency_ms": round(lookup_ms, 2),
                "saved_time_ms": response["saved_time_ms"],
                "stats": ask_cache.stats(),
            }
            ser_ms = (_time.perf_counter() - ser_t0) * 1000
            record_stage_ms("serialization", ser_ms)
            record_stage_ms("response", max(0.0, elapsed_ms - lookup_ms))

            timings = timer.as_dict()
            timings["total"] = int(round(elapsed_ms))
            timings["cache"] = int(round(lookup_ms))
            timings["serialization"] = int(round(ser_ms))
            for k in (
                "planner",
                "retrieval",
                "download",
                "validation",
                "profiling",
                "eda",
                "visualization",
                "forecast",
                "insights",
            ):
                timings[k] = 0
            response["timings"] = timings
            if turn:
                response["message_id"] = turn.get("message_id")
                response["artifact_ids"] = turn.get("artifact_ids") or []
            # Observability labels for metrics store
            timer.cache_hit = True
            timer.success = True
            timer.route = "/v1/ask"
            timer.status_code = 200
            timer.chart_type = (
                response.get("last_chart_type")
                or (response.get("chart_spec") or {}).get("chart_type")
            )
            timer.forecast_model = (
                response.get("forecast_model")
                or (response.get("forecast_meta") or {}).get("model")
            )
            logger.info(
                "Ask completed from cache",
                extra={
                    "session_id": session_id,
                    "timings": timings,
                    "cache_latency_ms": lookup_ms,
                    "saved_time_ms": response["saved_time_ms"],
                    "response_ms": elapsed_ms,
                },
            )
            # Payload already JSON-safe from store; light wrap only
            return response

        state = _build_state(
            session=session,
            question=question,
            file_path=normalized_file_path,
        )
        state["session_id"] = session_id
        state["user_id"] = user_id

        if normalized_file_path:
            state["file_path"] = normalized_file_path

        # Phase 5: load → inject memory hierarchy into LangGraph state
        memory_bundle = None
        try:
            with time_stage("session"):
                memory_bundle = memory_svc.load(
                    session_id,
                    user_id=user_id,
                    question=question,
                    dataset_topic=getattr(session, "dataset_topic", None) if session else None,
                    dataset_url=getattr(session, "dataset_url", None) if session else None,
                    dataset_path=(
                        normalized_file_path
                        if normalized_file_path
                        and not _is_remote_reference(normalized_file_path)
                        else (getattr(session, "dataset_path", None) if session else None)
                    ),
                    dataset_id=None,
                )
                state = memory_svc.inject_into_state(state, memory_bundle)
        except Exception as mem_exc:
            logger.warning(
                "Memory hierarchy load failed on ask",
                extra={"session_id": session_id, "error": str(mem_exc)},
            )

        # Phase 6: restore prior checkpoint (crash recovery / continuity) into state
        try:
            from backend.graph.state_codec import merge_checkpoint_into_state

            ckpt_svc = get_checkpoint_service()
            if ckpt_svc.has_checkpoint(session_id) and not state.get("topic_mismatch"):
                with time_stage("session"):
                    resumed = ckpt_svc.resume_session(
                        session_id, question=question, base_state=state
                    )
                    if resumed.get("resumable") and resumed.get("graph_state"):
                        # Keep this turn's question / upload path
                        restored = resumed["graph_state"]
                        restored["question"] = question
                        if normalized_file_path:
                            restored["file_path"] = normalized_file_path
                        state = merge_checkpoint_into_state(
                            state, restored, prefer_checkpoint=True
                        )
                        state["question"] = question
                        if normalized_file_path:
                            state["file_path"] = normalized_file_path
                        state["checkpoint_restored"] = True
                        state["restored_checkpoint_id"] = (
                            (resumed.get("checkpoint") or {}).get("checkpoint_id")
                        )
        except Exception as ckpt_exc:
            logger.warning(
                "Checkpoint restore skipped on ask",
                extra={"session_id": session_id, "error": str(ckpt_exc)},
            )

        try:
            result = _invoke_graph(state, session_id)

            # Phase 1: store assistant message + charts/forecast/EDA artifacts
            try:
                with time_stage("session"):
                    turn = session_svc.record_assistant_turn(
                        session_id,
                        question=question,
                        result=result,
                        file_path=normalized_file_path,
                        user_id=user_id,
                    )
            except Exception as persist_exc:
                logger.warning(
                    "Session assistant-turn persist failed; falling back to legacy save",
                    extra={"session_id": session_id, "error": str(persist_exc)},
                )
                turn = None
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
                    "dataset_topic": result.get("dataset_topic")
                    or result.get("dataset_name")
                    or result.get("dataset_title"),
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

            # Phase 5: persist L2 session + L3 dataset memory after the turn
            try:
                with time_stage("session"):
                    memory_svc.persist(
                        session_id,
                        result,
                        user_id=user_id,
                        question=question,
                        prior=memory_bundle,
                    )
            except Exception as mem_exc:
                logger.warning(
                    "Memory hierarchy persist failed on ask",
                    extra={"session_id": session_id, "error": str(mem_exc)},
                )

            # Phase 6: durable turn checkpoint after successful graph run
            with time_stage("session"):
                ckpt = _save_turn_checkpoint(session_id, result)

            # Session Reliability v2: never respond until session+memory are readable
            try:
                from backend.sessions.transactions import finalize_session_write

                with time_stage("session"):
                    finalize_session_write(
                        session_id,
                        user_id=user_id,
                        expect_messages=bool(turn),
                    )
            except Exception as fin_exc:
                logger.warning(
                    "Session finalize barrier soft-failed",
                    extra={"session_id": session_id, "error": str(fin_exc)},
                )

            ser_t0 = _time.perf_counter()
            with time_stage("serialization"):
                response = _stable_response(result, question=question)
            ser_ms = (_time.perf_counter() - ser_t0) * 1000
            if isinstance(response, dict):
                response["session_id"] = session_id
                response["user_id"] = user_id
                if turn:
                    response["message_id"] = turn.get("message_id")
                    response["artifact_ids"] = turn.get("artifact_ids") or []
                response["memory_hierarchy_loaded"] = bool(
                    state.get("memory_hierarchy_loaded")
                )
                if ckpt:
                    response["checkpoint_id"] = ckpt.get("checkpoint_id")
                    response["checkpoint_saved"] = True
                if state.get("checkpoint_restored"):
                    response["checkpoint_restored"] = True
                    response["restored_checkpoint_id"] = state.get(
                        "restored_checkpoint_id"
                    )

                # --- Ask-level cache store (final answer + charts/EDA/forecast) ---
                try:
                    with time_stage("cache"):
                        store_fp = (
                            result.get("dataset_fingerprint")
                            or cache_fp
                            or resolve_dataset_fingerprint(
                                file_path=normalized_file_path
                                if normalized_file_path
                                and not _is_remote_reference(normalized_file_path)
                                else None,
                                dataset_path=result.get("local_path")
                                or result.get("file_path"),
                                dataset_url=result.get("dataset_url"),
                                data=result.get("data"),
                            )
                        )
                        if not store_fp and result.get("data") is not None:
                            store_fp = compute_dataset_fingerprint(
                                result.get("data"),
                                result.get("dataset_url") or normalized_file_path,
                            )
                        cold_ms = (_time.perf_counter() - ask_t0) * 1000
                        if store_fp and not response.get("needs_user_data"):
                            ask_cache.put(
                                store_fp,
                                question,
                                response,
                                intent=intent,
                                file_path=normalized_file_path,
                                cold_ms=cold_ms,
                            )
                            response["dataset_fingerprint"] = store_fp
                        response["cache_hit"] = False
                        response["cache_skipped_pipeline"] = False
                        response["response_ms"] = round(cold_ms, 2)
                        response["cache"] = {
                            "cache_hit": False,
                            "fingerprint": store_fp,
                            "intent": intent,
                            "stats": ask_cache.stats(),
                        }
                except Exception as cache_store_exc:
                    logger.warning(
                        "Ask cache store failed",
                        extra={"error": str(cache_store_exc)},
                    )

                # Ensure timings always present with wall total
                resp_t0 = _time.perf_counter()
                timings = response.get("timings") or timer.as_dict()
                wall_ms = (_time.perf_counter() - ask_t0) * 1000
                timings["total"] = int(round(wall_ms))
                timings["serialization"] = int(
                    round(timings.get("serialization") or ser_ms)
                )
                # Response stage ≈ remaining assembly after serialization start
                record_stage_ms("response", (_time.perf_counter() - resp_t0) * 1000 + 0.1)
                timings["response"] = int(
                    round(timer.stages.get("response") or 0)
                ) or timings.get("response", 0)
                response["timings"] = timings

                # Observability: labels for SQLite sample on pipeline_timer exit
                timer.cache_hit = False
                timer.success = True
                timer.route = "/v1/ask"
                timer.status_code = 200
                timer.chart_type = (
                    result.get("last_chart_type")
                    or response.get("last_chart_type")
                    or (result.get("chart_spec") or {}).get("chart_type")
                )
                timer.forecast_model = (
                    result.get("forecast_model")
                    or (result.get("forecast_meta") or {}).get("model")
                    or (result.get("forecast_result") or {}).get("model")
                )
                # Provider latency from open-data / orchestrator metrics if present
                orch = (
                    (result.get("metadata") or {}).get("orchestrator")
                    or (result.get("retrieval_metrics") or {})
                    or {}
                )
                prov_lat = (
                    orch.get("metrics", {}).get("provider_latency_ms")
                    if isinstance(orch.get("metrics"), dict)
                    else None
                ) or result.get("provider_latency_ms")
                if isinstance(prov_lat, dict):
                    for pname, pms in prov_lat.items():
                        try:
                            timer.record_provider_latency(str(pname), float(pms))
                        except Exception:
                            pass
                elif result.get("provider") or result.get("dataset_provider"):
                    timer.provider = result.get("provider") or result.get(
                        "dataset_provider"
                    )

                logger.info(
                    "Ask completed",
                    extra={
                        "session_id": session_id,
                        "timings": timings,
                        "cache_hit": False,
                    },
                )

            return response
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
                    "timings": timer.as_dict(),
                },
            )
