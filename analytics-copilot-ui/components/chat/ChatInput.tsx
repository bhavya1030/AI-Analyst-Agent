"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import { askQuestion } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
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
  } = useChatStore();

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
        // Prefer open-data discovery for named public topics so a sticky upload
        // (or old file_path) does not force the wrong dataset (e.g. GDP vs gold).
        const lower = text.trim().toLowerCase();
        const shouldPreferDiscovery =
          /analyze|analyse|study|explore|forecast|predict|dataset about|data on/.test(lower) &&
          !/(upload|this file|my file|\.csv|\.xlsx)/.test(lower) &&
          /(gold|silver|oil|bitcoin|gdp|population|inflation|covid|climate|stock|unemployment)/.test(
            lower
          );

        const payload = await askQuestion(
          text.trim(),
          sessionId,
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
      } catch {
        setError("Backend unreachable. Start the API at http://localhost:8000.");
        addMessage({
          id: `assistant-error-${Date.now()}`,
          role: "assistant",
          text: "I could not reach the analytics backend. Please ensure the server is running.",
          timestamp: Date.now(),
        });
      } finally {
        setLoading(false);
        setPrompt("");
      }
    },
    [
      addMessage,
      filePath,
      sessionId,
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
        <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-soft transition focus-within:border-blue-400 focus-within:shadow-[0_0_0_3px_rgba(37,99,235,0.1)]">
          <textarea
            id="question"
            rows={2}
            className="max-h-36 min-h-[44px] flex-1 resize-none border-0 bg-transparent px-2.5 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 disabled:opacity-60"
            placeholder='Ask anything… e.g. "Analyze India GDP" or paste a CSV URL'
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
            className="btn-primary h-10 w-10 shrink-0 !rounded-xl !p-0"
            aria-label="Send message"
          >
            {loading ? <Loader2 className="animate-spin" size={16} /> : <ArrowUp size={16} />}
          </button>
        </div>
      </form>
      <div className="mt-1.5 flex items-center justify-between gap-2 px-1">
        <p className="text-[11px] text-slate-400">
          {filePath ? (
            <span className="text-emerald-600">Using uploaded file for this chat</span>
          ) : (
            "No upload — open-data discovery enabled"
          )}
        </p>
        {error ? <p className="text-[11px] font-medium text-red-500">{error}</p> : null}
      </div>
    </div>
  );
}
