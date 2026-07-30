"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import { askQuestion } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { ChatMessage } from "@/types";

/** True when the prompt looks like open-world discovery (not "use this file"). */
function prefersOpenDataDiscovery(text: string): boolean {
  const lower = text.trim().toLowerCase();
  if (!lower) return false;
  if (/(upload|this file|my file|\.csv|\.xlsx|this dataset)/.test(lower)) {
    return false;
  }
  const hasAnalyzeVerb =
    /analyze|analyse|study|explore|forecast|predict|dataset about|data on|find data/.test(
      lower
    );
  const hasSubject =
    /(gold|silver|oil|bitcoin|gdp|population|inflation|covid|climate|stock|unemployment|rainfall|co2|emission|temperature|sales|salary|employee)/.test(
      lower
    );
  return hasAnalyzeVerb && hasSubject;
}

/** Heuristic: prompt names a different subject than the bound dataset label. */
function isTopicSwitch(text: string, datasetName: string, filePath: string): boolean {
  if (!filePath && !datasetName) return false;
  const lower = text.trim().toLowerCase();
  const bound = `${datasetName} ${filePath}`.toLowerCase();
  // Common subjects
  const subjects = [
    "gold",
    "oil",
    "gdp",
    "population",
    "inflation",
    "bitcoin",
    "rainfall",
    "co2",
    "unemployment",
    "weather",
    "salary",
  ];
  for (const s of subjects) {
    if (lower.includes(s) && !bound.includes(s) && prefersOpenDataDiscovery(text)) {
      return true;
    }
  }
  return prefersOpenDataDiscovery(text) && Boolean(filePath);
}

export default function ChatInput() {
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState("");
  const inFlightRef = useRef(false);

  const addMessage = useChatStore((s) => s.addMessage);
  const sessionId = useChatStore((s) => s.sessionId);
  const filePath = useChatStore((s) => s.filePath);
  const datasetName = useChatStore((s) => s.datasetName);
  const loading = useChatStore((s) => s.loading);
  const beginAnalysis = useChatStore((s) => s.beginAnalysis);
  const completeAnalysis = useChatStore((s) => s.completeAnalysis);
  const failAnalysis = useChatStore((s) => s.failAnalysis);
  const ensureServerSession = useChatStore((s) => s.ensureServerSession);
  const setAnalysisTab = useUiStore((s) => s.setAnalysisTab);
  const pushNotification = useUiStore((s) => s.pushNotification);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) {
        setError("Enter a question to continue.");
        return;
      }
      // Hard guard against double-submit / double-click
      if (inFlightRef.current || useChatStore.getState().loading) {
        return;
      }
      inFlightRef.current = true;

      setError("");
      const requestId = `req-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        text: trimmed,
        timestamp: Date.now(),
      };

      // 1) Append user turn
      addMessage(userMessage);
      // 2) Clear canvas projection + mark in-flight (single source of truth)
      beginAnalysis(requestId);

      try {
        const activeSessionId = await ensureServerSession(
          trimmed.slice(0, 60) || "New analysis"
        );

        // Snapshot binding after session ensure (may have updated ids)
        const snap = useChatStore.getState();
        const topicSwitch = isTopicSwitch(trimmed, snap.datasetName, snap.filePath);
        const openDiscovery = prefersOpenDataDiscovery(trimmed) || topicSwitch;
        // Never send a stale file when the user is asking about a new open-data topic
        const pathForRequest =
          openDiscovery || topicSwitch ? undefined : snap.filePath || undefined;

        const payload = await askQuestion(
          trimmed,
          activeSessionId || snap.sessionId || sessionId,
          pathForRequest
        );

        // Abort if a newer request superseded this one
        if (useChatStore.getState().pendingRequestId !== requestId) {
          return;
        }

        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          text: payload.answer || "No answer returned.",
          charts:
            payload.charts?.map((chart, index) => ({
              ...chart,
              id: chart.id || `chart-${Date.now()}-${index}`,
              type: chart.type || "Chart",
              figure: chart.figure ?? chart,
            })) ||
            (payload.chart && Object.keys(payload.chart as object).length
              ? [
                  {
                    id: `chart-${Date.now()}`,
                    type: "Chart",
                    figure: payload.chart,
                  },
                ]
              : []),
          forecast: payload.forecast?.length
            ? {
                chart: payload.forecast_chart,
                values: payload.forecast,
                explanation: payload.chart_explanation || "",
              }
            : null,
          hypotheses: payload.hypotheses || [],
          suggestions: payload.recommended_next_steps || [],
          needsUserData: Boolean(payload.needs_user_data),
          acquisitionOptions: payload.data_acquisition_options || [],
          relatedDatasets: payload.related_datasets || [],
          discovery: payload.dataset_discovery || null,
          source: payload.source || "",
          timestamp: Date.now(),
        };

        // Resolve dataset binding from response (authoritative)
        const nextTopic =
          payload.dataset_topic ||
          (payload as any).dataset_name ||
          (payload.dataset_discovery as any)?.title ||
          undefined;
        const nextPath =
          (payload as any).local_path ||
          (payload as any).file_path ||
          (payload as any).dataset_path ||
          undefined;

        const accepted = completeAnalysis(requestId, assistantMessage, {
          datasetName: nextTopic,
          filePath: nextPath,
          // Clear stale upload when we switched to open-data discovery
          clearFilePath: Boolean(openDiscovery || topicSwitch) && !nextPath,
        });

        if (!accepted) return;

        // Surface results on the canvas
        if (payload.forecast?.length) setAnalysisTab("forecast");
        else if (payload.charts?.length || payload.chart) setAnalysisTab("charts");
        else setAnalysisTab("overview");
      } catch {
        setError("Backend unreachable. Start the API at http://localhost:8000.");
        failAnalysis(requestId, {
          id: `assistant-error-${Date.now()}`,
          role: "assistant",
          text: "I could not reach the analytics backend. Please ensure the server is running.",
          timestamp: Date.now(),
        });
        pushNotification({
          title: "Backend unreachable",
          body: "Could not complete analysis. Check that the API is running.",
          kind: "warning",
        });
      } finally {
        inFlightRef.current = false;
        setPrompt("");
      }
    },
    [
      addMessage,
      beginAnalysis,
      completeAnalysis,
      ensureServerSession,
      failAnalysis,
      pushNotification,
      sessionId,
      setAnalysisTab,
    ]
  );

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ text: string }>).detail;
      if (detail?.text && !useChatStore.getState().loading && !inFlightRef.current) {
        void sendMessage(detail.text);
      }
    };
    window.addEventListener("copilot:ask", handler);
    return () => window.removeEventListener("copilot:ask", handler);
  }, [sendMessage]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await sendMessage(prompt);
  };

  return (
    <div className="shrink-0">
      <form className="relative" onSubmit={handleSubmit}>
        <div className="flex items-end gap-2 rounded-2xl border border-border bg-surface p-1.5 shadow-soft transition focus-within:border-accent focus-within:shadow-glow">
          <textarea
            id="question"
            rows={2}
            className="max-h-32 min-h-[40px] flex-1 resize-none border-0 bg-transparent px-2.5 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-60"
            placeholder='Ask anything… e.g. "Analyze India GDP"'
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!loading && !inFlightRef.current) void sendMessage(prompt);
              }
            }}
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !prompt.trim()}
            className="btn-primary h-9 w-9 shrink-0 !rounded-xl !p-0"
            aria-label="Send message"
          >
            {loading ? <Loader2 className="animate-spin" size={15} /> : <ArrowUp size={15} />}
          </button>
        </div>
      </form>
      <div className="mt-1 flex items-center justify-between gap-2 px-1">
        <p className="text-[10px] text-muted-foreground">
          {filePath ? (
            <span className="text-success">
              Using uploaded file{datasetName ? ` · ${datasetName}` : ""}
            </span>
          ) : (
            "Open-data discovery enabled"
          )}
        </p>
        {error ? <p className="text-[10px] font-medium text-danger">{error}</p> : null}
      </div>
    </div>
  );
}
