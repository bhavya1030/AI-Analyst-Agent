"""Automatic conversation summarization (Phase 7).

When a session's message count exceeds a threshold:
  - Fold older messages into ``conversation_summary``
  - Keep the most recent N messages intact (is_summarized=False)
  - Preserve analytical context (dataset, charts, forecasts, filters, columns, insights)

Uses Ollama when ``USE_LLM_SUMMARY`` is enabled; otherwise a deterministic
extractive summary that never requires the LLM.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from backend.config import settings
from backend.core.logger import get_logger
from backend.db import SessionLocal
from backend.sessions.models import AnalysisSession, SessionArtifact, SessionMessage
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cfg_threshold() -> int:
    return max(4, int(getattr(settings, "CONVERSATION_SUMMARY_THRESHOLD", 20) or 20))


def _cfg_keep_recent() -> int:
    return max(2, int(getattr(settings, "CONVERSATION_SUMMARY_KEEP_RECENT", 12) or 12))


def _use_llm() -> bool:
    return bool(getattr(settings, "USE_LLM_SUMMARY", False))


class ConversationSummarizer:
    """Fold long chat history into a durable analytical summary."""

    def maybe_summarize(self, session_id: str) -> dict[str, Any] | None:
        """
        Run summarization if the session exceeds the message threshold.

        Returns a result dict when work was done, else None.
        """
        sid = (session_id or "").strip()
        if not sid:
            return None

        threshold = _cfg_threshold()
        keep_recent = _cfg_keep_recent()

        db = SessionLocal()
        try:
            session = (
                db.query(AnalysisSession)
                .filter(AnalysisSession.session_id == sid)
                .first()
            )
            if session is None:
                return None

            messages = (
                db.query(SessionMessage)
                .filter(SessionMessage.session_id == sid)
                .order_by(SessionMessage.seq.asc())
                .all()
            )
            total = len(messages)
            if total <= threshold:
                return None

            # Only fold messages that are still "active" (not already summarized)
            active = [m for m in messages if not bool(getattr(m, "is_summarized", False))]
            if len(active) <= keep_recent:
                return None
            # Need enough overflow beyond keep_recent
            if len(active) <= keep_recent:
                return None

            to_fold = active[:-keep_recent]
            if not to_fold:
                return None

            artifacts = (
                db.query(SessionArtifact)
                .filter(SessionArtifact.session_id == sid)
                .order_by(SessionArtifact.created_at.asc())
                .all()
            )

            context = self._collect_analytical_context(session, messages, artifacts)
            previous_summary = (session.conversation_summary or "").strip()

            fold_payload = [
                {
                    "role": m.role,
                    "content": (m.content or "")[:2000],
                    "seq": m.seq,
                }
                for m in to_fold
            ]

            summary_text, engine = self._build_summary(
                previous_summary=previous_summary,
                folded_messages=fold_payload,
                context=context,
            )
            if not summary_text:
                return None

            group_id = str(uuid.uuid4())
            for m in to_fold:
                m.is_summarized = True
                m.summary_group_id = group_id

            session.conversation_summary = summary_text[:8000]
            session.updated_at = _utcnow()
            db.commit()

            # Refresh FTS so summary is searchable
            try:
                from backend.sessions.search import upsert_session_fts

                upsert_session_fts(sid)
            except Exception:
                pass

            logger.info(
                "Conversation summarized",
                extra={
                    "session_id": sid,
                    "folded": len(to_fold),
                    "kept_recent": keep_recent,
                    "total_messages": total,
                    "engine": engine,
                    "summary_group_id": group_id,
                },
            )
            return {
                "session_id": sid,
                "folded_count": len(to_fold),
                "kept_recent": keep_recent,
                "total_messages": total,
                "summary_group_id": group_id,
                "engine": engine,
                "conversation_summary": session.conversation_summary,
            }
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Conversation summarization failed",
                extra={"session_id": sid, "error": str(exc)},
            )
            return None
        finally:
            db.close()

    def _collect_analytical_context(
        self,
        session: AnalysisSession,
        messages: list[SessionMessage],
        artifacts: list[SessionArtifact],
    ) -> dict[str, Any]:
        chart_types: list[str] = []
        forecast_notes: list[str] = []
        insight_snippets: list[str] = []
        columns: list[str] = []

        if session.last_columns:
            columns.extend(str(c) for c in (session.last_columns or []) if c)
        if session.last_used_columns:
            for c in session.last_used_columns or []:
                if c and str(c) not in columns:
                    columns.append(str(c))
        if session.last_chart_type:
            chart_types.append(str(session.last_chart_type))
        if session.last_forecast_target:
            forecast_notes.append(f"target={session.last_forecast_target}")
        if session.last_insight:
            insight_snippets.append(str(session.last_insight)[:300])

        for art in artifacts:
            kind = (art.kind or "").lower()
            meta = art.meta if isinstance(art.meta, dict) else {}
            content = art.content
            if kind == "chart":
                ct = meta.get("chart_type")
                if not ct and isinstance(content, dict):
                    ct = content.get("type")
                if ct and str(ct) not in chart_types:
                    chart_types.append(str(ct))
                cols = meta.get("columns_used") or []
                for c in cols:
                    if c and str(c) not in columns:
                        columns.append(str(c))
            elif kind == "forecast":
                tgt = meta.get("target") or session.last_forecast_target
                if tgt:
                    note = f"target={tgt}"
                    if note not in forecast_notes:
                        forecast_notes.append(note)
                if isinstance(content, dict) and content.get("values"):
                    forecast_notes.append(f"points={len(content.get('values') or [])}")
            elif kind in {"insight", "analysis_result"}:
                if isinstance(content, dict):
                    text = content.get("text") or content.get("answer")
                    if text:
                        insight_snippets.append(str(text)[:300])
                    for ins in content.get("insights") or []:
                        insight_snippets.append(str(ins)[:200])

        # memory_state filters / metrics
        filters: list[str] = []
        metrics: list[str] = []
        mem = session.memory_state if isinstance(session.memory_state, dict) else {}
        for f in mem.get("filters") or []:
            if isinstance(f, dict):
                filters.append(str(f.get("label") or f))
            else:
                filters.append(str(f))
        for m in mem.get("metrics") or []:
            metrics.append(str(m))

        operations = []
        if session.last_operation:
            operations.append(str(session.last_operation))
        if session.last_intent:
            operations.append(f"intent={session.last_intent}")

        # Questions from user messages (for continuity)
        questions = [
            (m.content or "").strip()[:160]
            for m in messages
            if (m.role or "") == "user" and (m.content or "").strip()
        ][-8:]

        return sanitize_for_json(
            {
                "dataset_topic": session.dataset_topic or session.dataset_name or "",
                "dataset_url": session.dataset_url or "",
                "dataset_path": session.dataset_path or "",
                "dataset_id": session.dataset_id or "",
                "columns": columns[:40],
                "chart_types": chart_types[:15],
                "forecasts": forecast_notes[:10],
                "filters": filters[:20],
                "metrics": metrics[:20],
                "insights": insight_snippets[:12],
                "operations": operations[:10],
                "questions": questions,
                "eda_rows": (session.eda_summary or {}).get("rows")
                if isinstance(session.eda_summary, dict)
                else None,
                "eda_time_columns": (session.eda_summary or {}).get("time_columns")
                if isinstance(session.eda_summary, dict)
                else None,
            }
        ) or {}

    def _build_summary(
        self,
        *,
        previous_summary: str,
        folded_messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> tuple[str, str]:
        """Return (summary_text, engine_name)."""
        deterministic = self._deterministic_summary(
            previous_summary=previous_summary,
            folded_messages=folded_messages,
            context=context,
        )
        if not _use_llm():
            return deterministic, "deterministic"

        try:
            llm_text = self._llm_summary(
                previous_summary=previous_summary,
                folded_messages=folded_messages,
                context=context,
            )
            if llm_text and len(llm_text.strip()) > 40:
                # Always append structured analytical block for reliability
                structured = self._analytical_block(context)
                combined = f"{llm_text.strip()}\n\n{structured}".strip()
                if previous_summary:
                    # Keep prior analytical facts if LLM omitted them
                    combined = self._merge_previous(previous_summary, combined, context)
                return combined[:8000], "llm"
        except Exception as exc:
            logger.info(
                "LLM summary failed; using deterministic fallback",
                extra={"error": str(exc)},
            )
        return deterministic, "deterministic"

    def _deterministic_summary(
        self,
        *,
        previous_summary: str,
        folded_messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> str:
        lines: list[str] = []
        lines.append("## Conversation summary (analytical)")
        lines.append(self._analytical_block(context))

        # Folded dialogue highlights
        user_qs = [
            m["content"]
            for m in folded_messages
            if m.get("role") == "user" and m.get("content")
        ]
        asst = [
            m["content"]
            for m in folded_messages
            if m.get("role") == "assistant" and m.get("content")
        ]
        if user_qs:
            lines.append("### Questions covered")
            for q in user_qs[-6:]:
                lines.append(f"- {q[:200]}")
        if asst:
            lines.append("### Assistant findings (excerpt)")
            for a in asst[-4:]:
                snippet = " ".join(str(a).split())[:240]
                lines.append(f"- {snippet}")

        body = "\n".join(lines).strip()
        if previous_summary:
            # Prefer newer structured block; keep unique lines from previous
            prev_lines = [
                ln for ln in previous_summary.splitlines() if ln.strip() and ln not in body
            ]
            if prev_lines:
                body = (
                    previous_summary.strip()
                    + "\n\n---\n\n"
                    + body
                )
        return body[:8000]

    def _analytical_block(self, context: dict[str, Any]) -> str:
        parts = []
        topic = context.get("dataset_topic") or "unknown"
        parts.append(f"- Dataset: {topic}")
        if context.get("dataset_url"):
            parts.append(f"- Dataset URL: {context['dataset_url']}")
        if context.get("dataset_path"):
            parts.append(f"- Dataset path: {context['dataset_path']}")
        if context.get("dataset_id"):
            parts.append(f"- Dataset id: {context['dataset_id']}")
        if context.get("columns"):
            parts.append(f"- Columns used: {', '.join(context['columns'][:20])}")
        if context.get("chart_types"):
            parts.append(f"- Charts: {', '.join(context['chart_types'])}")
        if context.get("forecasts"):
            parts.append(f"- Forecasts: {', '.join(context['forecasts'])}")
        if context.get("filters"):
            parts.append(f"- Filters: {', '.join(context['filters'][:10])}")
        if context.get("metrics"):
            parts.append(f"- Metrics: {', '.join(context['metrics'][:10])}")
        if context.get("operations"):
            parts.append(f"- Operations: {', '.join(context['operations'])}")
        if context.get("eda_rows") is not None:
            parts.append(f"- EDA rows: {context['eda_rows']}")
        if context.get("eda_time_columns"):
            parts.append(f"- Time columns: {', '.join(map(str, context['eda_time_columns']))}")
        if context.get("insights"):
            parts.append("- Insights:")
            for ins in context["insights"][:6]:
                parts.append(f"  - {ins}")
        return "\n".join(parts)

    def _merge_previous(
        self, previous: str, current: str, context: dict[str, Any]
    ) -> str:
        # Ensure analytical block keys present
        block = self._analytical_block(context)
        if "Dataset:" not in current and block:
            return f"{current}\n\n{block}"[:8000]
        return current[:8000]

    def _llm_summary(
        self,
        *,
        previous_summary: str,
        folded_messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> str:
        from backend.llm.ollama_client import invoke_llm

        transcript = "\n".join(
            f"{m.get('role', 'user').upper()}: {m.get('content', '')[:800]}"
            for m in folded_messages[-30:]
        )
        prompt = f"""You summarize a data-analysis chat for an analytics copilot.
Preserve analytical facts. Do not invent data.

Existing summary:
{previous_summary or "(none)"}

Analytical context (must preserve):
{self._analytical_block(context)}

Older messages to fold:
{transcript}

Write a concise summary (max 350 words) covering:
1) Active dataset and key columns
2) Analyses / charts / forecasts performed
3) Filters or focus entities
4) Important insights and open questions
Plain text only. No JSON.
"""
        return (invoke_llm(prompt) or "").strip()


_summarizer: ConversationSummarizer | None = None


def get_conversation_summarizer() -> ConversationSummarizer:
    global _summarizer
    if _summarizer is None:
        _summarizer = ConversationSummarizer()
    return _summarizer


def maybe_summarize_session(session_id: str) -> dict[str, Any] | None:
    """Module-level entry used after each assistant turn."""
    return get_conversation_summarizer().maybe_summarize(session_id)
