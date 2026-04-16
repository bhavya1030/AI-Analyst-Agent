"use client";

import { useChatStore } from "@/store/chatStore";
import { askQuestion } from "@/services/api";
import { ChatMessage } from "@/types";

interface SuggestionsPanelProps {
  suggestions?: string[];
}

export default function SuggestionsPanel({ suggestions }: SuggestionsPanelProps) {
  const { suggestions: storeSuggestions, setSuggestions, addMessage, sessionId, setLoading, setHypotheses, setForecast, setDatasetName } = useChatStore();
  const items = suggestions ?? storeSuggestions;

  const handleClick = async (text: string) => {
    setLoading(true);
    const userMessage: ChatMessage = { id: `user-${Date.now()}`, role: "user", text };
    addMessage(userMessage);
    setSuggestions([]);

    try {
      const payload = await askQuestion(text, sessionId);
      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        text: payload.answer || "No answer returned.",
        charts: payload.charts?.map((chart) => ({
          ...chart,
          id: chart.id || `chart-${Date.now()}-${Math.random()}`,
        })) || [],
        forecast: payload.forecast?.length ? { chart: payload.forecast_chart, values: payload.forecast, explanation: payload.chart_explanation || "" } : null,
        hypotheses: payload.hypotheses || [],
        suggestions: payload.recommended_next_steps || [],
      };
      addMessage(assistantMessage);
      setSuggestions(payload.recommended_next_steps || []);
      setHypotheses(payload.hypotheses || []);
      setForecast(payload.forecast?.length ? { chart: payload.forecast_chart, values: payload.forecast, explanation: payload.chart_explanation || "" } : null);
      if (payload.dataset_topic) {
        setDatasetName(payload.dataset_topic);
      }
    } catch {
      // Silence, handle in UI later if necessary
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">Next steps</h3>
        <span className="text-sm text-slate-500 dark:text-slate-400">Session {sessionId}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">No recommended next questions yet.</p>
      ) : (
        <div className="space-y-3">
          {items.map((option) => (
            <button
              key={option}
              type="button"
              className="w-full rounded-2xl border border-slate-200 bg-slate-100 px-4 py-3 text-left text-sm text-slate-700 transition hover:border-slate-300 hover:bg-slate-200 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:hover:bg-slate-900"
              onClick={() => handleClick(option)}
            >
              {option}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
