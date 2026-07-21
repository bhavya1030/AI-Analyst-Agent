import json

from backend.config import settings
from backend.core.logger import get_logger
from backend.llm.ollama_client import invoke_llm

logger = get_logger(__name__)


def insight_agent(state):
    """Produce the final user-facing answer for the analytics copilot.

    Combines prior agent outputs (EDA, charts, forecasts, comparisons,
    recommendations) into a coherent executive-style response.
    """
    parts: list[str] = []

    existing_answer = (state.get("answer") or "").strip()
    if existing_answer:
        parts.append(existing_answer)

    # Forecast-specific note
    if state.get("forecast") and "forecast" not in existing_answer.lower():
        parts.append("Forecast generated using a time-series model.")

    # Build narrative when no agent left a useful answer.
    if not parts:
        narrative = _build_rule_based_narrative(state)
        if narrative:
            parts.append(narrative)

    # Optional LLM polish for richer analysis when we have structure but thin text.
    if not parts or (len(parts) == 1 and len(parts[0]) < 80 and state.get("insights")):
        llm_answer = _try_llm_insight(state)
        if llm_answer:
            parts = [llm_answer]

    if not parts:
        parts.append("Analysis complete. Ask a follow-up such as 'forecast it' or 'visualize trends'.")

    # Always surface recommended next steps for conversational continuity.
    recommendations = state.get("recommended_next_steps") or []
    if not recommendations:
        # Lazy recommendation if earlier agent was skipped.
        try:
            from backend.agents.recommendation_agent import recommendation_agent

            state = recommendation_agent(state)
            recommendations = state.get("recommended_next_steps") or []
        except Exception:
            recommendations = []

    if recommendations:
        rec_text = "Suggested next steps: " + "; ".join(recommendations[:4])
        if rec_text.lower() not in " ".join(parts).lower():
            parts.append(rec_text)

    # Mention active dataset so the user knows memory is working.
    topic = state.get("dataset_topic")
    if topic and state.get("data") is not None:
        memory_note = f"Active dataset in this session: {topic}."
        if memory_note.lower() not in " ".join(parts).lower():
            parts.append(memory_note)

    state["answer"] = " ".join(part.strip() for part in parts if part and part.strip())
    return state


def _build_rule_based_narrative(state) -> str:
    chunks: list[str] = []
    topic = state.get("dataset_topic") or "the dataset"
    profile = state.get("dataset_profile") or {}
    focus = state.get("focus_country")

    if state.get("rows"):
        scope = f"Analyzed {topic}"
        if focus:
            scope += f" focused on {focus}"
        scope += f" ({state.get('rows')} rows"
        cols = state.get("columns") or profile.get("column_names") or []
        if cols:
            scope += f", {len(cols)} columns"
        scope += ")."
        chunks.append(scope)

    insights = state.get("insights") or []
    for item in insights:
        if not isinstance(item, dict):
            continue
        if "error" in item:
            continue
        if "rows" in item and "describe" in item:
            missing = item.get("missing_values") or {}
            missing_total = sum(int(v) for v in missing.values() if isinstance(v, (int, float)))
            if missing_total == 0:
                chunks.append("No missing values detected in the prepared frame.")
            describe = item.get("describe") or {}
            # Highlight a few numeric means if present.
            highlighted = 0
            for col, stats in describe.items():
                if highlighted >= 2:
                    break
                if isinstance(stats, dict) and isinstance(stats.get("mean"), (int, float)):
                    chunks.append(f"Average {col} is {round(stats['mean'], 2)}.")
                    highlighted += 1

    if state.get("detected_patterns"):
        patterns = state["detected_patterns"]
        if isinstance(patterns, list) and patterns:
            chunks.append("Patterns: " + "; ".join(str(p) for p in patterns[:3]) + ".")

    if state.get("hypotheses"):
        hyps = state["hypotheses"]
        if isinstance(hyps, list) and hyps:
            chunks.append("Hypothesis: " + str(hyps[0]))

    if state.get("chart") or state.get("charts"):
        chunks.append("Charts were generated to illustrate the key trends.")

    if state.get("chart_explanation"):
        chunks.append(str(state["chart_explanation"]))

    if profile:
        numeric = profile.get("numeric_columns") or []
        time_cols = profile.get("time_columns") or []
        if time_cols and numeric:
            chunks.append(
                f"Time series structure detected ({time_cols[0]} with numeric measures) — forecasting is available."
            )

    return " ".join(chunks)


def _try_llm_insight(state) -> str:
    insights = state.get("insights", [])
    dataset_explanation = state.get("dataset_explanation", [])
    dataset_profile = state.get("dataset_profile", {})
    recommended_next_steps = state.get("recommended_next_steps", [])
    question = state.get("question") or ""

    if not insights and not dataset_profile and not dataset_explanation:
        return ""

    summary = insights[0] if insights else {}
    summary_text = _format_insight_summary(summary)

    prompt = f"""
You are a senior data analyst speaking to a business user.

User question: {question}
Dataset topic: {state.get("dataset_topic")}
Focus country: {state.get("focus_country")}

Dataset Profile:
{json.dumps(dataset_profile, indent=2)[:2000]}

EDA Summary:
{summary_text[:2000]}

Recommendations:
{json.dumps(recommended_next_steps, indent=2)}

Write a concise executive response with:
1) What the data shows
2) Key insights
3) Risks or caveats
4) What to do next

Plain text only. Keep under 200 words.
"""

    logger.info("LLM INSIGHT AGENT INVOKED", extra={"model": settings.OLLAMA_MODEL})
    try:
        response = invoke_llm(prompt)
        if response and response.strip():
            return response.strip()
    except Exception as exc:
        logger.warning("Insight LLM failed", extra={"error": str(exc)})
    return ""


def _format_insight_summary(summary):
    if isinstance(summary, str):
        return summary
    if isinstance(summary, dict):
        try:
            return json.dumps(summary, indent=2)
        except Exception:
            return str(summary)
    return str(summary)
