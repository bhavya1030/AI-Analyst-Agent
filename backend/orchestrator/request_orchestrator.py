"""Request orchestrator — coordinates the ask and analyze pipelines.

Extracted verbatim from backend/main.py (/ask and /analyze handlers).
No FastAPI dependency: accepts plain Python args, returns plain dicts.
Logic is identical to main.py; only location changed.
"""

from __future__ import annotations

import threading
import time as _time
from typing import Any

from fastapi.responses import JSONResponse

from backend.core.logger import get_logger
from backend.graph.checkpoint_service import get_checkpoint_service
from backend.graph.workflow import build_graph
from backend.memory.hierarchy import get_memory_hierarchy
from backend.orchestrator.response_builder import build_stable_response
from backend.orchestrator.state_builder import (
    SessionSnapshot,
    build_analyst_state,
    get_session_snapshot,
    is_remote_reference,
    normalize_dataset_reference,
)
from backend.sessions.service import SessionAccessDenied, get_session_service
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal graph helpers (moved from main.py, unchanged)
# ---------------------------------------------------------------------------


def _graph_config(session_id: str) -> dict:
    """LangGraph runnable config: thread_id ties checkpoints to the session."""
    return {"configurable": {"thread_id": session_id or "default"}}


def _invoke_graph(graph, state: dict, session_id: str):
    """Invoke graph with session-scoped checkpointing when available."""
    try:
        return graph.invoke(state, _graph_config(session_id))
    except TypeError:
        return graph.invoke(state)
    except Exception as exc:
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


# ---------------------------------------------------------------------------
# RequestOrchestrator
# ---------------------------------------------------------------------------


class RequestOrchestrator:
    """Coordinates the ask and analyze pipelines without FastAPI coupling.

    Both ``run_ask`` and ``run_analyze`` are pure Python callables that take
    plain args and return plain dicts (or JSONResponse for error cases).
    They are independently testable without an HTTP test client.
    """

    def __init__(self, graph=None) -> None:
        self._graph = graph or build_graph()

    # ------------------------------------------------------------------
    # /analyze pipeline
    # ------------------------------------------------------------------

    def run_analyze(self, *, session_id: str, user_id: str) -> Any:
        """Run the analyze pipeline.  Returns a response dict or JSONResponse."""
        session_svc = get_session_service()
        memory_svc = get_memory_hierarchy()

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

        session = get_session_snapshot(session_id)
        state = build_analyst_state(session=session, question="analyze dataset")
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
            result = _invoke_graph(self._graph, state, session_id)

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

            # Phase 1: durable session turn
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
                    "Session persistence failed on analyze",
                    extra={"session_id": session_id, "error": str(persist_exc)},
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

            # Phase 6: durable turn checkpoint
            ckpt = _save_turn_checkpoint(session_id, result)
            response = build_stable_response(result)
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

    # ------------------------------------------------------------------
    # /ask pipeline
    # ------------------------------------------------------------------

    def run_ask(
        self,
        *,
        question: str,
        session_id: str,
        file_path: str | None,
        user_id: str,
    ) -> Any:
        """Run the full ask pipeline.  Returns a response dict or JSONResponse."""
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
            normalized_file_path = normalize_dataset_reference(file_path)
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
                session = get_session_snapshot(session_id)

            # --- Topic switch: release stale upload even if client still sends it ---
            topic_switch = False
            try:
                from backend.memory.topic_switch import (
                    log_dataset_binding_decision,
                    release_bound_file_if_topic_switch,
                )

                released_path, topic_switch = release_bound_file_if_topic_switch(
                    question,
                    normalized_file_path,
                    session_topic=getattr(session, "dataset_topic", None) if session else None,
                    session_name=(
                        getattr(session, "dataset_name", None) if session else None
                    )
                    or (getattr(session, "dataset_topic", None) if session else None),
                    session_path=getattr(session, "dataset_path", None) if session else None,
                )
                if topic_switch:
                    logger.info(
                        "ASK_TOPIC_SWITCH",
                        extra={
                            "incoming_prompt": (question or "")[:120],
                            "released_file_path": normalized_file_path,
                            "session_topic": getattr(session, "dataset_topic", None)
                            if session
                            else None,
                            "session_path": getattr(session, "dataset_path", None)
                            if session
                            else None,
                        },
                    )
                normalized_file_path = released_path
            except Exception as ts_exc:
                logger.warning(
                    "Topic switch detect failed",
                    extra={"error": str(ts_exc)},
                )
                topic_switch = False

            # --- Ask-level cache lookup ---
            with time_stage("cache"):
                cache_fp = None
                if session is not None and not topic_switch:
                    try:
                        from backend.memory.hierarchy_store import load_session_memory_blob

                        blob = load_session_memory_blob(session_id) or {}
                        cache_fp = blob.get("dataset_fingerprint") or None
                    except Exception:
                        cache_fp = None
                if not cache_fp and not topic_switch:
                    cache_fp = resolve_dataset_fingerprint(
                        file_path=normalized_file_path
                        if normalized_file_path and not is_remote_reference(normalized_file_path)
                        else None,
                        dataset_path=getattr(session, "dataset_path", None) if session else None,
                        dataset_url=getattr(session, "dataset_url", None) if session else None,
                    )
                elif not cache_fp and normalized_file_path:
                    cache_fp = resolve_dataset_fingerprint(
                        file_path=normalized_file_path
                        if not is_remote_reference(normalized_file_path)
                        else None,
                        dataset_path=None,
                        dataset_url=None,
                    )

                cached_body, cache_meta = (None, {})
                if cache_fp and not topic_switch:
                    cached_body, cache_meta = ask_cache.get(
                        cache_fp,
                        question,
                        intent=intent,
                        file_path=normalized_file_path,
                    )
                elif topic_switch:
                    logger.info(
                        "Cache skipped due to topic switch",
                        extra={"prompt": (question or "")[:80]},
                    )

            try:
                from backend.memory.topic_switch import log_dataset_binding_decision

                log_dataset_binding_decision(
                    prompt=question,
                    planner_topic=None,
                    current_dataset=getattr(session, "dataset_topic", None) if session else None,
                    reuse_dataset=not topic_switch and bool(
                        normalized_file_path
                        or (session and (session.dataset_path or session.dataset_url))
                    ),
                    topic_mismatch=topic_switch,
                    file_path=normalized_file_path,
                    cache_key=cache_fp,
                )
            except Exception:
                pass

            # --- Warm path (cache hit) ---
            if cached_body:
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
                lookup_ms = float(
                    cache_meta.get("lookup_ms") or cache_meta.get("cache_latency_ms") or 0
                )
                cold_ms = cache_meta.get("cold_ms")
                saved_ms = cache_meta.get("saved_time_ms")
                if saved_ms is None and cold_ms is not None:
                    try:
                        saved_ms = max(0.0, float(cold_ms) - elapsed_ms)
                    except Exception:
                        saved_ms = None

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
                    "planner", "retrieval", "download", "validation",
                    "profiling", "eda", "visualization", "forecast", "insights",
                ):
                    timings[k] = 0
                response["timings"] = timings
                if turn:
                    response["message_id"] = turn.get("message_id")
                    response["artifact_ids"] = turn.get("artifact_ids") or []
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
                return response

            # --- Cold path ---
            state = build_analyst_state(
                session=session,
                question=question,
                file_path=normalized_file_path,
            )
            state["session_id"] = session_id
            state["user_id"] = user_id
            state["question"] = question
            topic_switch = bool(state.get("topic_mismatch") or topic_switch)
            if topic_switch:
                state["topic_mismatch"] = True
                state["force_reload_dataset"] = True
                state["reuse_active_dataset"] = False
                normalized_file_path = None

            # Phase 5: load → inject memory hierarchy
            memory_bundle = None
            try:
                with time_stage("session"):
                    memory_bundle = memory_svc.load(
                        session_id,
                        user_id=user_id,
                        question=question,
                        dataset_topic=(
                            None
                            if topic_switch
                            else (getattr(session, "dataset_topic", None) if session else None)
                        ),
                        dataset_url=(
                            None
                            if topic_switch
                            else (getattr(session, "dataset_url", None) if session else None)
                        ),
                        dataset_path=(
                            normalized_file_path
                            if normalized_file_path
                            and not is_remote_reference(normalized_file_path)
                            else (
                                None
                                if topic_switch
                                else (
                                    getattr(session, "dataset_path", None) if session else None
                                )
                            )
                        ),
                        dataset_id=None,
                    )
                    state = memory_svc.inject_into_state(state, memory_bundle)
                    if topic_switch:
                        from backend.memory.topic_switch import apply_topic_switch_to_state

                        state = apply_topic_switch_to_state(state)
            except Exception as mem_exc:
                logger.warning(
                    "Memory hierarchy load failed on ask",
                    extra={"session_id": session_id, "error": str(mem_exc)},
                )

            # Phase 6: restore prior checkpoint
            try:
                from backend.graph.state_codec import merge_checkpoint_into_state

                ckpt_svc = get_checkpoint_service()
                if ckpt_svc.has_checkpoint(session_id) and not state.get("topic_mismatch"):
                    with time_stage("session"):
                        resumed = ckpt_svc.resume_session(
                            session_id, question=question, base_state=state
                        )
                        if resumed.get("resumable") and resumed.get("graph_state"):
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
                result = _invoke_graph(self._graph, state, session_id)

                # Phase 1: persist assistant turn
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
                        "Session assistant-turn persist failed",
                        extra={"session_id": session_id, "error": str(persist_exc)},
                    )
                    turn = None

                # Phase 5: persist memory hierarchy
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

                # Phase 6: turn checkpoint
                with time_stage("session"):
                    ckpt = _save_turn_checkpoint(session_id, result)

                # Session Reliability v2: read-after-write barrier
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
                    response = build_stable_response(result, question=question)
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

                    # Cache store
                    try:
                        with time_stage("cache"):
                            store_fp = (
                                result.get("dataset_fingerprint")
                                or cache_fp
                                or resolve_dataset_fingerprint(
                                    file_path=normalized_file_path
                                    if normalized_file_path
                                    and not is_remote_reference(normalized_file_path)
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

                    # Final timings
                    resp_t0 = _time.perf_counter()
                    timings = response.get("timings") or timer.as_dict()
                    wall_ms = (_time.perf_counter() - ask_t0) * 1000
                    timings["total"] = int(round(wall_ms))
                    timings["serialization"] = int(
                        round(timings.get("serialization") or ser_ms)
                    )
                    record_stage_ms(
                        "response", (_time.perf_counter() - resp_t0) * 1000 + 0.1
                    )
                    timings["response"] = int(
                        round(timer.stages.get("response") or 0)
                    ) or timings.get("response", 0)
                    response["timings"] = timings

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


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_orchestrator: RequestOrchestrator | None = None
_orchestrator_lock = threading.Lock()


def get_orchestrator() -> RequestOrchestrator:
    """Return the shared RequestOrchestrator, building it on first call."""
    global _orchestrator
    with _orchestrator_lock:
        if _orchestrator is None:
            _orchestrator = RequestOrchestrator()
    return _orchestrator
