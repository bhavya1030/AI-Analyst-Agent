"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Loader2, Send } from "lucide-react";
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
        setError("Please enter a question to continue.");
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
        const payload = await askQuestion(text.trim(), sessionId, filePath || undefined);
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
    <div className="border-t border-slate-100 pt-3 dark:border-slate-800">
      <form className="flex items-end gap-2" onSubmit={handleSubmit}>
        <div className="flex-1">
          <textarea
            id="question"
            rows={2}
            className="w-full resize-none rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-sky-400 dark:focus:ring-sky-900"
            placeholder='Ask anything… e.g. "Analyze India GDP" or "Forecast it for 10 years"'
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
          {filePath ? (
            <p className="mt-1 px-1 text-[11px] text-emerald-600 dark:text-emerald-400">
              Using uploaded file for this chat
            </p>
          ) : (
            <p className="mt-1 px-1 text-[11px] text-slate-400">
              No upload — agent may auto-discover open data
            </p>
          )}
        </div>
        <button
          type="submit"
          disabled={loading}
          className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-sky-600 text-white shadow-sm transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-400"
          aria-label="Send message"
        >
          {loading ? <Loader2 className="animate-spin" size={18} /> : <Send size={18} />}
        </button>
      </form>
      {error ? <p className="mt-2 text-sm text-red-500">{error}</p> : null}
    </div>
  );
}
