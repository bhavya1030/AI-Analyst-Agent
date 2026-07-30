"""Memory hierarchy service (Phase 5).

Request lifecycle:
  load(session) → inject_into_state(state) → graph.invoke → persist(session, result)

Levels:
  L1 Conversation — last N messages (from session_messages)
  L2 Session      — current analysis working set (session row + memory_state)
  L3 Dataset      — prior work on same dataset (dataset_memory table)
  L4 Knowledge    — learned_datasets + dataset
"""

from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any

from backend.core.logger import get_logger
from backend.memory.hierarchy_models import (
    ConversationMemory,
    ConversationMessage,
    DatasetMemory,
    KnowledgeMemory,
    MemoryBundle,
    SessionMemory,
    _utc_now_iso,
)
from backend.memory.hierarchy_store import (
    ensure_dataset_memory_schema,
    load_session_memory_blob,
    make_dataset_key,
    resolve_dataset_memory,
    save_dataset_memory,
    save_session_memory_blob,
)
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)

DEFAULT_L1_WINDOW = 12
MAX_INSIGHT_DIGEST = 30


class MemoryHierarchyService:
    """Load / inject / persist the four-level memory hierarchy."""

    def __init__(self, *, l1_window: int = DEFAULT_L1_WINDOW):
        self.l1_window = max(2, int(l1_window or DEFAULT_L1_WINDOW))
        ensure_dataset_memory_schema()
        self._ensure_session_memory_column()

    @staticmethod
    def _ensure_session_memory_column() -> None:
        """Add analysis_sessions.memory_state if missing (SQLite ALTER)."""
        try:
            from sqlalchemy import inspect, text

            from backend.db import engine
            from backend.sessions.service import ensure_session_tables

            ensure_session_tables()
            with engine.begin() as conn:
                insp = inspect(conn)
                if "analysis_sessions" not in insp.get_table_names():
                    return
                cols = {c["name"] for c in insp.get_columns("analysis_sessions")}
                if "memory_state" not in cols:
                    conn.execute(
                        text(
                            "ALTER TABLE analysis_sessions "
                            "ADD COLUMN memory_state JSON"
                        )
                    )
                    logger.info("Added analysis_sessions.memory_state column")
        except Exception as exc:
            logger.debug(
                "memory_state column ensure skipped",
                extra={"error": str(exc)},
            )

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(
        self,
        session_id: str,
        *,
        user_id: str = "anonymous",
        question: str | None = None,
        dataset_fingerprint: str | None = None,
        dataset_topic: str | None = None,
        dataset_url: str | None = None,
        dataset_path: str | None = None,
        dataset_id: str | None = None,
    ) -> MemoryBundle:
        """Assemble L1–L4 for the current request."""
        from backend.sessions.service import get_session_service

        session_svc = get_session_service()
        session_svc.ensure_session(session_id, user_id=user_id)

        # --- L1: recent messages ---
        l1 = self._load_l1(session_id)

        # --- L2: session analysis memory ---
        l2 = self._load_l2(session_id, user_id=user_id)

        # Prefer live session bindings when caller did not pass dataset identity
        topic = dataset_topic or l2.dataset_topic
        url = dataset_url or l2.dataset_url
        path = dataset_path or l2.dataset_path
        ds_id = dataset_id or l2.dataset_id
        fp = dataset_fingerprint or l2.dataset_fingerprint

        # --- L3: dataset-scoped memory ---
        l3 = self._load_l3(
            user_id=user_id,
            fingerprint=fp,
            dataset_id=ds_id,
            dataset_url=url,
            dataset_path=path,
            dataset_topic=topic,
        )

        # --- L4: knowledge / registry ---
        topic_hint = topic or self._topic_from_question(question) or ""
        l4 = self._load_l4(topic_hint)

        bundle = MemoryBundle(
            session_id=session_id,
            user_id=user_id or "anonymous",
            l1_conversation=l1,
            l2_session=l2,
            l3_dataset=l3,
            l4_knowledge=l4,
            loaded_at=_utc_now_iso(),
        )
        logger.info(
            "Memory hierarchy loaded",
            extra={
                "session_id": session_id,
                "l1_messages": len(l1.messages),
                "l3_key": l3.dataset_key or None,
                "l4_learned": len(l4.learned_datasets),
                "l4_registry": len(l4.registry_datasets),
            },
        )
        return bundle

    def _load_l1(self, session_id: str) -> ConversationMemory:
        from backend.db import SessionLocal
        from backend.sessions.models import AnalysisSession, SessionMessage

        db = SessionLocal()
        try:
            summary = ""
            sess = (
                db.query(AnalysisSession)
                .filter(AnalysisSession.session_id == session_id)
                .first()
            )
            if sess is not None:
                summary = getattr(sess, "conversation_summary", None) or ""

            # Prefer recent non-summarized messages (Phase 7 keeps these intact)
            q = db.query(SessionMessage).filter(
                SessionMessage.session_id == session_id
            )
            try:
                # is_summarized may be missing on very old DBs before migration
                active = (
                    q.filter(SessionMessage.is_summarized.is_(False))
                    .order_by(SessionMessage.seq.desc())
                    .limit(self.l1_window)
                    .all()
                )
            except Exception:
                active = []
            if active:
                rows = list(reversed(active))
            else:
                rows = list(
                    reversed(
                        q.order_by(SessionMessage.seq.desc())
                        .limit(self.l1_window)
                        .all()
                    )
                )
            messages = [
                ConversationMessage(
                    role=m.role or "user",
                    content=m.content or "",
                    seq=m.seq,
                    message_id=m.id,
                )
                for m in rows
            ]
            # L1 anchors: previous user question + latest assistant response + intent
            previous_question = None
            current_response = None
            current_intent = None
            for m in reversed(messages):
                if previous_question is None and m.role == "user":
                    previous_question = m.content
                if current_response is None and m.role == "assistant":
                    current_response = m.content
                if previous_question and current_response:
                    break
            if sess is not None:
                current_intent = getattr(sess, "last_intent", None)
            return ConversationMemory(
                messages=messages,
                window_size=self.l1_window,
                conversation_summary=str(summary or ""),
                current_intent=current_intent,
                previous_question=previous_question,
                current_response=(current_response or "")[:2000] or None,
            )
        finally:
            db.close()

    def _load_l2(self, session_id: str, *, user_id: str) -> SessionMemory:
        from backend.db import SessionLocal
        from backend.sessions.models import AnalysisSession

        blob = load_session_memory_blob(session_id) or {}
        db = SessionLocal()
        try:
            row = (
                db.query(AnalysisSession)
                .filter(AnalysisSession.session_id == session_id)
                .first()
            )
            if row is None:
                mem = SessionMemory.from_dict(blob)
                mem.session_id = session_id
                return mem

            # Prefer live columns; fill gaps from blob
            base = SessionMemory(
                session_id=session_id,
                last_intent=row.last_intent or blob.get("last_intent"),
                last_operation=row.last_operation or blob.get("last_operation"),
                last_chart_type=row.last_chart_type or blob.get("last_chart_type"),
                last_forecast_target=row.last_forecast_target
                or blob.get("last_forecast_target"),
                last_columns=list(row.last_columns or blob.get("last_columns") or []),
                last_column=row.last_column or blob.get("last_column"),
                selected_columns=list(
                    blob.get("selected_columns")
                    or row.last_used_columns
                    or row.last_columns
                    or []
                ),
                dataset_topic=row.dataset_topic or blob.get("dataset_topic"),
                dataset_id=row.dataset_id or blob.get("dataset_id"),
                dataset_path=row.dataset_path or blob.get("dataset_path"),
                dataset_url=row.dataset_url or blob.get("dataset_url"),
                dataset_fingerprint=blob.get("dataset_fingerprint"),
                dataset_name=row.dataset_name or blob.get("dataset_name"),
                dataset_profile_summary=dict(
                    row.eda_summary or blob.get("dataset_profile_summary") or {}
                ),
                metrics=list(blob.get("metrics") or []),
                entities=list(blob.get("entities") or []),
                filters=list(blob.get("filters") or []),
                chart_types=list(blob.get("chart_types") or []),
                artifact_ids=list(blob.get("artifact_ids") or []),
                forecast_model=blob.get("forecast_model"),
                forecast_horizon=blob.get("forecast_horizon"),
                has_forecast=bool(blob.get("has_forecast")),
                last_insight=row.last_insight or blob.get("last_insight"),
                last_query=row.last_query or blob.get("last_query"),
                hypotheses=list(blob.get("hypotheses") or []),
                recommended_next_steps=list(blob.get("recommended_next_steps") or []),
                detected_patterns=list(blob.get("detected_patterns") or []),
            )
            return base
        finally:
            db.close()

    def _load_l3(
        self,
        *,
        user_id: str,
        fingerprint: str | None,
        dataset_id: str | None,
        dataset_url: str | None,
        dataset_path: str | None,
        dataset_topic: str | None,
    ) -> DatasetMemory:
        existing = resolve_dataset_memory(
            user_id or "anonymous",
            fingerprint=fingerprint,
            dataset_id=dataset_id,
            dataset_url=dataset_url,
            dataset_path=dataset_path,
            dataset_topic=dataset_topic,
        )
        if existing is not None:
            return existing
        key = make_dataset_key(
            fingerprint=fingerprint,
            dataset_id=dataset_id,
            dataset_url=dataset_url,
            dataset_path=dataset_path,
            dataset_topic=dataset_topic,
        )
        return DatasetMemory(
            dataset_key=key,
            dataset_fingerprint=fingerprint,
            dataset_topic=dataset_topic,
            dataset_url=dataset_url,
            dataset_path=dataset_path,
            dataset_id=dataset_id,
        )

    def _load_l4(self, topic_hint: str) -> KnowledgeMemory:
        learned: list[dict[str, Any]] = []
        registry: list[dict[str, Any]] = []
        try:
            from backend.memory.learned_datasets import list_learned_datasets, recall_datasets

            if topic_hint:
                learned = recall_datasets(topic_hint, limit=5) or []
            if not learned:
                learned = list_learned_datasets(limit=10) or []
        except Exception as exc:
            logger.debug("L4 learned load failed", extra={"error": str(exc)})

        try:
            from backend.registry.service import DatasetRegistryService

            svc = DatasetRegistryService()
            if topic_hint:
                hits = svc.get_by_topic(topic_hint, limit=5) or []
                registry = [h.to_dict() if hasattr(h, "to_dict") else dict(h) for h in hits]
            if not registry:
                hits = svc.list_datasets(limit=10, active_only=True) or []
                registry = [
                    h.to_dict() if hasattr(h, "to_dict") else dict(h) for h in hits
                ]
        except Exception as exc:
            logger.debug("L4 registry load failed", extra={"error": str(exc)})

        return KnowledgeMemory(
            learned_datasets=sanitize_for_json(learned) or [],
            registry_datasets=sanitize_for_json(registry) or [],
            topic_hint=topic_hint or "",
        )

    @staticmethod
    def _topic_from_question(question: str | None) -> str:
        if not question:
            return ""
        # Lightweight: first meaningful tokens (agents refine later)
        stop = {
            "the", "a", "an", "analyze", "forecast", "show", "plot", "please",
            "data", "dataset", "for", "of", "and", "next", "years",
        }
        tokens = [
            t
            for t in __import__("re").findall(r"[a-z0-9]+", question.lower())
            if len(t) > 2 and t not in stop
        ]
        return " ".join(tokens[:4])

    # ------------------------------------------------------------------
    # Inject into LangGraph state
    # ------------------------------------------------------------------

    def inject_into_state(self, state: dict[str, Any], bundle: MemoryBundle) -> dict[str, Any]:
        """
        Merge hierarchy into graph state without overwriting active request fields
        that are already intentionally set (e.g. fresh file_path).

        Critical: detect topic mismatch *before* rebinding session dataset paths
        so "Analyze gold" after "India GDP" never silently reuses the GDP file.
        """
        state = state if isinstance(state, dict) else {}
        l1, l2, l3, l4 = (
            bundle.l1_conversation,
            bundle.l2_session,
            bundle.l3_dataset,
            bundle.l4_knowledge,
        )

        # --- Pre-detect topic switch before path/frame injection ---
        if not state.get("topic_mismatch") and not state.get("file_path"):
            try:
                from backend.memory.continuity import is_new_dataset_topic

                question = state.get("question") or state.get("raw_question")
                active_topic = l2.dataset_topic or l2.dataset_name
                has_binding = bool(
                    l2.dataset_path
                    or l2.dataset_url
                    or l2.dataset_fingerprint
                    or l3.dataset_path
                    or l3.dataset_url
                )
                if has_binding and is_new_dataset_topic(
                    question,
                    active_topic,
                    has_active_dataset=has_binding,
                ):
                    state["topic_mismatch"] = True
                    state["force_reload_dataset"] = True
                    state["reuse_active_dataset"] = False
                    # Do not carry prior topic labels into discovery
                    state.pop("dataset_topic", None)
                    logger.info(
                        "Topic mismatch pre-detect — skip session dataset rebind",
                        extra={
                            "question": (question or "")[:80],
                            "active_topic": active_topic,
                        },
                    )
            except Exception as exc:
                logger.debug(
                    "Topic mismatch pre-detect skipped",
                    extra={"error": str(exc)},
                )

        # Full structured bundle (agents may read selectively)
        state["memory"] = sanitize_for_json(bundle.to_dict())
        state["conversation_memory"] = sanitize_for_json(l1.to_dict())
        state["session_memory"] = sanitize_for_json(l2.to_dict())
        state["dataset_memory"] = sanitize_for_json(l3.to_dict())
        state["knowledge_memory"] = sanitize_for_json(l4.to_dict())
        state["memory_hierarchy_loaded"] = True
        state["session_id"] = state.get("session_id") or bundle.session_id

        # L1 → recent dialogue for context agents
        state["recent_messages"] = [
            {"role": m.role, "content": m.content, "seq": m.seq}
            for m in l1.messages
        ]
        if l1.conversation_summary and not state.get("conversation_summary"):
            state["conversation_summary"] = l1.conversation_summary
        if l1.previous_question and not state.get("previous_question"):
            state["previous_question"] = l1.previous_question
        if l1.current_response and not state.get("previous_response"):
            state["previous_response"] = l1.current_response
        if l1.current_intent and not state.get("last_intent"):
            state["last_intent"] = l1.current_intent

        # L2 → continuity fields only when empty (do not fight topic_mismatch clears)
        if not state.get("topic_mismatch"):
            if not state.get("last_intent") and l2.last_intent:
                state["last_intent"] = l2.last_intent
            if not state.get("last_operation") and l2.last_operation:
                state["last_operation"] = l2.last_operation
            if not state.get("last_chart_type") and l2.last_chart_type:
                state["last_chart_type"] = l2.last_chart_type
            if not state.get("last_forecast_target") and l2.last_forecast_target:
                state["last_forecast_target"] = l2.last_forecast_target
            if not state.get("last_columns_used") and l2.last_columns:
                state["last_columns_used"] = list(l2.last_columns)
            if not state.get("last_column_used") and l2.last_column:
                state["last_column_used"] = l2.last_column
            if not state.get("selected_columns") and (
                l2.selected_columns or l2.last_columns
            ):
                state["selected_columns"] = list(l2.selected_columns or l2.last_columns)
            if not state.get("dataset_topic") and l2.dataset_topic:
                state["dataset_topic"] = l2.dataset_topic
            if not state.get("dataset_name") and l2.dataset_name:
                state["dataset_name"] = l2.dataset_name
            if not state.get("dataset_url") and l2.dataset_url:
                state["dataset_url"] = l2.dataset_url
            if not state.get("dataset_id") and l2.dataset_id:
                state["dataset_id"] = l2.dataset_id
            if not state.get("dataset_profile") and l2.dataset_profile_summary:
                state["dataset_profile"] = dict(l2.dataset_profile_summary)
            if not state.get("dataset_fingerprint") and l2.dataset_fingerprint:
                state["dataset_fingerprint"] = l2.dataset_fingerprint
            # Paths for reload / planner
            if l2.dataset_path:
                if not state.get("file_path"):
                    state["file_path"] = l2.dataset_path
                if not state.get("local_path"):
                    state["local_path"] = l2.dataset_path
                if not state.get("dataset_path"):
                    state["dataset_path"] = l2.dataset_path
            if l2.filters and not state.get("filters"):
                state["filters"] = list(l2.filters)
            if l2.metrics and not state.get("metrics"):
                state["metrics"] = list(l2.metrics)
            if l2.has_forecast and not state.get("forecast_model"):
                state["session_had_forecast"] = True
                if l2.forecast_model:
                    state["forecast_model"] = l2.forecast_model
            if l2.forecast_horizon and not state.get("forecast_horizon"):
                state["forecast_horizon"] = l2.forecast_horizon

        if l2.hypotheses and not state.get("hypotheses"):
            state["hypotheses"] = list(l2.hypotheses)
        if l2.recommended_next_steps and not state.get("recommended_next_steps"):
            state["recommended_next_steps"] = list(l2.recommended_next_steps)

        # L3 → prior dataset work as soft hints
        if l3.dataset_key:
            state["dataset_memory_key"] = l3.dataset_key
            if l3.columns_frequently_used and not state.get("preferred_columns"):
                state["preferred_columns"] = list(l3.columns_frequently_used)
            if l3.successful_chart_types and not state.get("preferred_chart_types"):
                state["preferred_chart_types"] = list(l3.successful_chart_types)
            if l3.insights_digest:
                state["prior_dataset_insights"] = list(l3.insights_digest)[-5:]
            if l3.analysis_count:
                state["dataset_prior_analysis_count"] = int(l3.analysis_count)
            # Path fallback from L3 when L2 path missing
            if not state.get("topic_mismatch"):
                if not state.get("file_path") and l3.dataset_path:
                    state["file_path"] = l3.dataset_path
                    state["local_path"] = state.get("local_path") or l3.dataset_path
                if not state.get("dataset_url") and l3.dataset_url:
                    state["dataset_url"] = l3.dataset_url
                if not state.get("dataset_fingerprint") and l3.dataset_fingerprint:
                    state["dataset_fingerprint"] = l3.dataset_fingerprint

        # L4 → related / known datasets (Knowledge Memory)
        related = []
        for item in (l4.learned_datasets or [])[:5]:
            if isinstance(item, dict):
                related.append(item)
        for item in (l4.registry_datasets or [])[:5]:
            if isinstance(item, dict) and item not in related:
                related.append(item)
        if related and not state.get("related_datasets"):
            state["related_datasets"] = related
        if l4.topic_hint and not state.get("knowledge_topic_hint"):
            state["knowledge_topic_hint"] = l4.topic_hint

        # --- Memory v2: auto-restore dataframe for planner ---
        if not state.get("topic_mismatch") and state.get("data") is None:
            try:
                from backend.memory.restore import apply_restored_frame, restore_dataframe

                df = restore_dataframe(
                    dataset_path=l2.dataset_path or state.get("dataset_path"),
                    dataset_url=l2.dataset_url or state.get("dataset_url"),
                    local_path=state.get("local_path"),
                    file_path=state.get("file_path"),
                )
                if df is not None:
                    apply_restored_frame(state, df)
                    state["session_dataframe_restored"] = True
            except Exception as exc:
                logger.warning(
                    "Session dataframe restore failed",
                    extra={"error": str(exc)},
                )

        # Planner injection flags — never request upload when dataset is bound
        try:
            from backend.memory.continuity import build_planner_injection

            state.update(build_planner_injection(state))
        except Exception:
            if state.get("data") is not None and not state.get("topic_mismatch"):
                state["reuse_active_dataset"] = True
                state["has_active_dataset"] = True
                state["needs_user_data"] = False
                state["planner_skip_upload"] = True

        return state
    # ------------------------------------------------------------------
    # Persist after graph run
    # ------------------------------------------------------------------

    def persist(
        self,
        session_id: str,
        result: dict[str, Any],
        *,
        user_id: str = "anonymous",
        question: str | None = None,
        prior: MemoryBundle | None = None,
    ) -> MemoryBundle:
        """Update L2 + L3 from graph result; L1 is message-backed; L4 is external."""
        result = result if isinstance(result, dict) else {}
        prior = prior or MemoryBundle(session_id=session_id, user_id=user_id)

        # Fingerprint if frame available
        fingerprint = result.get("dataset_fingerprint")
        if not fingerprint and result.get("data") is not None:
            try:
                from backend.cache.fingerprint import compute_dataset_fingerprint

                ref = (
                    result.get("dataset_url")
                    or result.get("file_path")
                    or result.get("local_path")
                )
                fingerprint = compute_dataset_fingerprint(result.get("data"), ref)
            except Exception:
                fingerprint = prior.l2_session.dataset_fingerprint

        # --- L2 ---
        l2 = deepcopy(prior.l2_session)
        l2.session_id = session_id
        l2.last_intent = result.get("last_intent") or l2.last_intent
        l2.last_operation = result.get("last_operation") or l2.last_operation
        l2.last_chart_type = result.get("last_chart_type") or l2.last_chart_type
        l2.last_forecast_target = (
            result.get("last_forecast_target") or l2.last_forecast_target
        )
        cols = result.get("last_columns_used") or result.get("columns") or l2.last_columns
        if cols:
            l2.last_columns = list(cols)[:50]
        if result.get("last_column_used"):
            l2.last_column = result.get("last_column_used")
        if result.get("dataset_topic"):
            l2.dataset_topic = result.get("dataset_topic")
        if result.get("dataset_id") or result.get("registry_id"):
            l2.dataset_id = result.get("dataset_id") or result.get("registry_id")
        if result.get("dataset_url"):
            l2.dataset_url = result.get("dataset_url")
        path = result.get("file_path") or result.get("local_path")
        if path and not str(path).startswith(("http://", "https://")):
            l2.dataset_path = str(path)
        if fingerprint:
            l2.dataset_fingerprint = fingerprint
        profile = result.get("dataset_profile") or {}
        if profile:
            # Keep a slim profile for memory (no huge describe dumps if nested)
            l2.dataset_profile_summary = sanitize_for_json(
                {
                    "rows": profile.get("rows"),
                    "columns": profile.get("columns") or profile.get("column_names"),
                    "numeric_columns": profile.get("numeric_columns"),
                    "categorical_columns": profile.get("categorical_columns"),
                    "time_columns": profile.get("time_columns"),
                    "recommended_analyses": profile.get("recommended_analyses"),
                }
            ) or {}
        if result.get("answer"):
            l2.last_insight = str(result.get("answer"))[:4000]
        if question:
            l2.last_query = question
        if result.get("hypotheses"):
            l2.hypotheses = list(result.get("hypotheses") or [])[:20]
        if result.get("recommended_next_steps"):
            l2.recommended_next_steps = list(result.get("recommended_next_steps") or [])[:20]
        if result.get("detected_patterns"):
            l2.detected_patterns = list(result.get("detected_patterns") or [])[:20]
        # Memory v2 session fields
        sel = result.get("selected_columns") or result.get("last_columns_used") or result.get("columns")
        if sel:
            l2.selected_columns = list(sel)[:50]
        if result.get("filters"):
            l2.filters = list(result.get("filters") or [])[:30]
        if result.get("dataset_name"):
            l2.dataset_name = result.get("dataset_name")
        if result.get("forecast") or result.get("forecast_chart"):
            l2.has_forecast = True
        if result.get("forecast_model"):
            l2.forecast_model = result.get("forecast_model")
        if result.get("forecast_horizon"):
            try:
                l2.forecast_horizon = int(result.get("forecast_horizon"))
            except Exception:
                pass
        chart_type = result.get("last_chart_type")
        if chart_type:
            types = list(l2.chart_types or [])
            if chart_type not in types:
                types.append(str(chart_type))
            l2.chart_types = types[-20:]
        if result.get("artifact_ids"):
            ids = list(l2.artifact_ids or [])
            for a in result.get("artifact_ids") or []:
                if a not in ids:
                    ids.append(a)
            l2.artifact_ids = ids[-50:]
        l2.updated_at = _utc_now_iso()

        save_session_memory_blob(session_id, sanitize_for_json(l2.to_dict()) or {})

        # --- L3 ---
        key = make_dataset_key(
            fingerprint=l2.dataset_fingerprint,
            dataset_id=l2.dataset_id,
            dataset_url=l2.dataset_url,
            dataset_path=l2.dataset_path,
            dataset_topic=l2.dataset_topic,
        )
        l3 = prior.l3_dataset
        if key:
            loaded = resolve_dataset_memory(
                user_id or "anonymous",
                fingerprint=l2.dataset_fingerprint,
                dataset_id=l2.dataset_id,
                dataset_url=l2.dataset_url,
                dataset_path=l2.dataset_path,
                dataset_topic=l2.dataset_topic,
            )
            if loaded is not None:
                l3 = loaded
            elif not l3.dataset_key:
                l3 = DatasetMemory(dataset_key=key)
            # Prefer strongest identity key (fingerprint) when available
            l3.dataset_key = key
            l3.dataset_fingerprint = l2.dataset_fingerprint
            l3.dataset_topic = l2.dataset_topic
            l3.dataset_url = l2.dataset_url
            l3.dataset_path = l2.dataset_path
            l3.dataset_id = l2.dataset_id
            l3.analysis_count = int(l3.analysis_count or 0) + 1

            # Merge columns
            for c in l2.last_columns or []:
                if c and c not in l3.columns_frequently_used:
                    l3.columns_frequently_used.append(str(c))
            l3.columns_frequently_used = l3.columns_frequently_used[:40]

            chart_type = l2.last_chart_type
            if chart_type and chart_type not in l3.successful_chart_types:
                l3.successful_chart_types.append(str(chart_type))
            l3.successful_chart_types = l3.successful_chart_types[:20]

            if l2.last_forecast_target:
                if l2.last_forecast_target not in l3.last_forecast_targets:
                    l3.last_forecast_targets.append(str(l2.last_forecast_target))
                l3.last_forecast_targets = l3.last_forecast_targets[:20]

            if l2.last_insight:
                digest = str(l2.last_insight)[:300]
                if digest not in l3.insights_digest:
                    l3.insights_digest.append(digest)
                l3.insights_digest = l3.insights_digest[-MAX_INSIGHT_DIGEST:]

            if session_id not in l3.last_session_ids:
                l3.last_session_ids.append(session_id)
            l3.last_session_ids = l3.last_session_ids[-20:]

            if l2.dataset_profile_summary:
                l3.last_profile_summary = dict(l2.dataset_profile_summary)

            l3.updated_at = _utc_now_iso()
            save_dataset_memory(user_id or "anonymous", l3)

        # L1 refreshed from messages on next load; L4 owned by registry/learned
        l1 = self._load_l1(session_id)
        l4 = prior.l4_knowledge

        bundle = MemoryBundle(
            session_id=session_id,
            user_id=user_id or "anonymous",
            l1_conversation=l1,
            l2_session=l2,
            l3_dataset=l3,
            l4_knowledge=l4,
            loaded_at=_utc_now_iso(),
        )
        logger.info(
            "Memory hierarchy persisted",
            extra={
                "session_id": session_id,
                "l3_key": l3.dataset_key or None,
                "l3_analyses": l3.analysis_count,
            },
        )
        return bundle


_service: MemoryHierarchyService | None = None
_service_lock = threading.Lock()


def get_memory_hierarchy() -> MemoryHierarchyService:
    global _service
    with _service_lock:
        if _service is None:
            _service = MemoryHierarchyService()
        return _service
