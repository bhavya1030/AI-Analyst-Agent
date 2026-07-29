"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import { askQuestion } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { ChatMessage } from "@/types";

export default function ChatInput() {
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState("");
  const {
    addMessage,
    sessionId,
    filePath,
    setLoading,
    loading,
    setSuggestions,
    setHypotheses,
    setForecast,
    setDatasetName,
    ensureServerSession,
  } = useChatStore();
  const setAnalysisTab = useUiStore((s) => s.setAnalysisTab);
  const pushNotification = useUiStore((s) => s.pushNotification);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim()) {
        setError("Enter a question to continue.");
        return;
      }

      setError("");
      setLoading(true);
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        text: text.trim(),
        timestamp: Date.now(),
      };
      addMessage(userMessage);

      try {
        const activeSessionId = await ensureServerSession(
          text.trim().slice(0, 60) || "New analysis"
        );

        const lower = text.trim().toLowerCase();
        const shouldPreferDiscovery =
          /analyze|analyse|study|explore|forecast|predict|dataset about|data on/.test(
            lower
          ) &&
          !/(upload|this file|my file|\.csv|\.xlsx)/.test(lower) &&
          /(gold|silver|oil|bitcoin|gdp|population|inflation|covid|climate|stock|unemployment)/.test(
            lower
          );

        const payload = await askQuestion(
          text.trim(),
          activeSessionId || sessionId,
          shouldPreferDiscovery ? undefined : filePath || undefined
        );
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

        addMessage(assistantMessage);
        setSuggestions(payload.recommended_next_steps || []);
        setHypotheses(payload.hypotheses || []);
        setForecast(
          payload.forecast?.length
            ? {
                chart: payload.forecast_chart,
                values: payload.forecast,
                explanation: payload.chart_explanation || "",
              }
            : null
        );
        if (payload.dataset_topic) {
          setDatasetName(payload.dataset_topic);
        }

        // Surface results on the canvas
        if (payload.forecast?.length) setAnalysisTab("forecast");
        else if (payload.charts?.length || payload.chart) setAnalysisTab("charts");
        else setAnalysisTab("overview");
      } catch {
        setError("Backend unreachable. Start the API at http://localhost:8000.");
        addMessage({
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
        setLoading(false);
        setPrompt("");
      }
    },
    [
      addMessage,
      ensureServerSession,
      filePath,
      pushNotification,
      sessionId,
      setAnalysisTab,
      setDatasetName,
      setForecast,
      setHypotheses,
      setLoading,
      setSuggestions,
    ]
  );

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ text: string }>).detail;
      if (detail?.text && !loading) {
        void sendMessage(detail.text);
      }
    };
    window.addEventListener("copilot:ask", handler);
    return () => window.removeEventListener("copilot:ask", handler);
  }, [loading, sendMessage]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await sendMessage(prompt);
  };

  return (
    <div>
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
                if (!loading) void sendMessage(prompt);
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
            <span className="text-success">Using uploaded file</span>
          ) : (
            "Open-data discovery enabled"
          )}
        </p>
        {error ? <p className="text-[10px] font-medium text-danger">{error}</p> : null}
      </div>
    </div>
  );
}
