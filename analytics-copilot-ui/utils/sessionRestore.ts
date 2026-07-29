/**
 * Map backend GET /sessions/{id} payloads into UI chat/state shapes.
 * Backend is the source of truth for history, charts, forecasts, dataset.
 */

import {
  ChatMessage,
  ChartPayload,
  ForecastResult,
  SessionDetail,
  SessionSnapshot,
} from "@/types";

function parseTimestamp(value?: string | null, fallback?: number): number {
  if (!value) return fallback || Date.now();
  const t = Date.parse(value);
  return Number.isFinite(t) ? t : fallback || Date.now();
}

function normalizeChart(raw: any, index: number, sessionId: string): ChartPayload | null {
  if (!raw) return null;

  // Artifact content may be the chart object itself
  let chart = raw;
  if (raw.kind === "chart" && raw.content != null) {
    chart = raw.content;
  }

  // Wrapped: { type, figure, columns_used }
  if (chart.figure || chart.type) {
    return {
      id: chart.id || `restored-chart-${sessionId}-${index}`,
      type: chart.type || chart.meta?.chart_type || "Chart",
      figure: chart.figure ?? chart,
      columns_used: chart.columns_used || chart.meta?.columns_used || [],
    };
  }

  // Raw plotly-like dict
  if (chart.data || chart.layout || typeof chart === "object") {
    return {
      id: `restored-chart-${sessionId}-${index}`,
      type: "Chart",
      figure: chart,
      columns_used: [],
    };
  }

  return null;
}

function normalizeForecast(raw: any): ForecastResult | null {
  if (!raw) return null;
  let payload = raw;
  if (raw.kind === "forecast" && raw.content) {
    payload = raw.content;
  }
  if (Array.isArray(payload)) {
    return { chart: {}, values: payload, explanation: "" };
  }
  if (typeof payload === "object") {
    const values = payload.values || payload.forecast || [];
    const chart = payload.chart || payload.forecast_chart || {};
    if (!values?.length && !chart?.data && !Object.keys(chart || {}).length) {
      return null;
    }
    return {
      chart,
      values: Array.isArray(values) ? values : [],
      explanation: payload.error || payload.explanation || "",
    };
  }
  return null;
}

function chartsFromDetail(detail: SessionDetail): ChartPayload[] {
  const sid = detail.session_id;
  const out: ChartPayload[] = [];
  const sources = [
    ...(detail.generated_charts || []),
    ...((detail.artifacts || []).filter((a) => (a.kind || "").toLowerCase() === "chart")),
  ];
  sources.forEach((raw, i) => {
    const c = normalizeChart(raw, i, sid);
    if (c) out.push(c);
  });
  return out;
}

function forecastsFromDetail(detail: SessionDetail): ForecastResult | null {
  const list = detail.forecast_results || [];
  if (list.length) {
    return normalizeForecast(list[list.length - 1]);
  }
  const art = (detail.artifacts || []).filter(
    (a) => (a.kind || "").toLowerCase() === "forecast"
  );
  if (art.length) {
    return normalizeForecast(art[art.length - 1]);
  }
  return null;
}

function analysisMetaFromDetail(detail: SessionDetail): {
  hypotheses: string[];
  suggestions: string[];
} {
  let hypotheses: string[] = [];
  let suggestions: string[] = [];

  for (const raw of detail.analysis_results || []) {
    const content = raw?.content ?? raw;
    if (content && typeof content === "object") {
      if (Array.isArray(content.hypotheses)) {
        hypotheses = content.hypotheses.map(String);
      }
      if (Array.isArray(content.recommended_next_steps)) {
        suggestions = content.recommended_next_steps.map(String);
      }
    }
  }

  for (const art of detail.artifacts || []) {
    const kind = (art.kind || "").toLowerCase();
    const content = art.content;
    if (kind === "hypothesis" && content && typeof content === "object") {
      if (Array.isArray(content.hypotheses)) {
        hypotheses = content.hypotheses.map(String);
      }
    }
    if (kind === "analysis_result" && content && typeof content === "object") {
      if (Array.isArray(content.hypotheses) && !hypotheses.length) {
        hypotheses = content.hypotheses.map(String);
      }
      if (Array.isArray(content.recommended_next_steps) && !suggestions.length) {
        suggestions = content.recommended_next_steps.map(String);
      }
    }
  }

  return { hypotheses, suggestions };
}

/**
 * Build chat messages from full backend session detail.
 * Prefers chat_history; falls back to last_query / last_insight.
 */
export function messagesFromSessionDetail(detail: SessionDetail): ChatMessage[] {
  const history = detail.chat_history || [];
  const charts = chartsFromDetail(detail);
  const forecast = forecastsFromDetail(detail);
  const { hypotheses, suggestions } = analysisMetaFromDetail(detail);

  if (history.length) {
    // Pair assistant turns with charts/forecasts when payload has artifact ids
    // or attach latest analysis artifacts to the last assistant message.
    let lastAssistantIdx = -1;
    const messages: ChatMessage[] = history.map((m, idx) => {
      const role = (m.role || "assistant").toLowerCase() === "user" ? "user" : "assistant";
      const base: ChatMessage = {
        id: m.id || `restored-${detail.session_id}-${m.seq ?? idx}`,
        role,
        text: m.content || "",
        timestamp: parseTimestamp(m.created_at, Date.now() - (history.length - idx) * 1000),
      };
      if (role === "assistant") {
        lastAssistantIdx = idx;
      }
      return base;
    });

    if (lastAssistantIdx >= 0) {
      messages[lastAssistantIdx] = {
        ...messages[lastAssistantIdx],
        charts: charts.length ? charts : messages[lastAssistantIdx].charts,
        forecast: forecast || messages[lastAssistantIdx].forecast || null,
        hypotheses: hypotheses.length ? hypotheses : messages[lastAssistantIdx].hypotheses,
        suggestions: suggestions.length ? suggestions : messages[lastAssistantIdx].suggestions,
      };
    }

    return messages;
  }

  // Legacy fallback
  const messages: ChatMessage[] = [];
  const ts = Date.now();
  if (detail.last_query) {
    messages.push({
      id: `restored-user-${detail.session_id}`,
      role: "user",
      text: detail.last_query,
      timestamp: ts - 1000,
    });
  }
  if (detail.last_insight || charts.length || forecast) {
    messages.push({
      id: `restored-assistant-${detail.session_id}`,
      role: "assistant",
      text: detail.last_insight || "Restored analysis results.",
      charts,
      forecast,
      hypotheses,
      suggestions,
      timestamp: ts,
    });
  }
  if (!messages.length) {
    messages.push({
      id: `restored-empty-${detail.session_id}`,
      role: "assistant",
      text: `Opened session “${detail.title || detail.session_id}”. ${
        detail.dataset_topic ? `Active topic: ${detail.dataset_topic}. ` : ""
      }Ask a follow-up to continue analysis.`,
      timestamp: ts,
    });
  }
  return messages;
}

export function snapshotFromSessionDetail(detail: SessionDetail): SessionSnapshot {
  const messages = messagesFromSessionDetail(detail);
  const lastAssistant =
    [...messages].reverse().find((m) => m.role === "assistant") || null;
  const charts = chartsFromDetail(detail);
  const forecast = forecastsFromDetail(detail);
  const { hypotheses, suggestions } = analysisMetaFromDetail(detail);

  const filePath =
    detail.dataset_path ||
    detail.current_dataset?.dataset_path ||
    detail.current_dataset?.local_path ||
    "";

  const datasetName =
    detail.dataset_name ||
    detail.dataset_topic ||
    detail.current_dataset?.dataset_topic ||
    "";

  return {
    sessionId: detail.session_id,
    datasetName,
    filePath: typeof filePath === "string" ? filePath : "",
    messages,
    charts: charts.length ? charts : lastAssistant?.charts || [],
    forecast: forecast || lastAssistant?.forecast || null,
    suggestions: suggestions.length ? suggestions : lastAssistant?.suggestions || [],
    hypotheses: hypotheses.length ? hypotheses : lastAssistant?.hypotheses || [],
    activeAssistantId: lastAssistant?.id || null,
    updatedAt: parseTimestamp(detail.updated_at || detail.last_activity_at),
    title: detail.title,
    favorite: Boolean(detail.favorite),
    archived: Boolean(detail.archived),
    pinned: Boolean(detail.pinned),
    status: detail.status || "active",
  };
}

export function parseServerTime(value?: string | null): number {
  return parseTimestamp(value, 0);
}
