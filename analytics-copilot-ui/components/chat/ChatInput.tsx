"use client";

import { FormEvent, useState } from "react";
import { Send, Upload } from "lucide-react";
import { askQuestion } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { ChatMessage } from "@/types";

export default function ChatInput() {
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState("");
  const { addMessage, sessionId, setLoading, loading, setSuggestions, setHypotheses, setForecast, setDatasetName } = useChatStore();

  const sendMessage = async (text: string) => {
    if (!text.trim()) {
      setError("Please enter a question to continue.");
      return;
    }

    setError("");
    setLoading(true);
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      text,
    };
    addMessage(userMessage);

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
    } catch (err) {
      setError("The backend is unreachable. Please check your connection.");
    } finally {
      setLoading(false);
      setPrompt("");
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await sendMessage(prompt);
  };

  return (
    <div className="mt-4 rounded-3xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
      <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
        <label htmlFor="question" className="text-sm font-medium text-slate-700 dark:text-slate-200">
          Ask your dataset
        </label>
        <div className="flex gap-2">
          <textarea
            id="question"
            rows={3}
            className="min-h-[96px] flex-1 rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-sky-400 dark:focus:ring-sky-900"
            placeholder='Upload a dataset first, then ask a question like "What are the most interesting correlations?"'
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading}
            className="inline-flex h-14 items-center justify-center rounded-2xl bg-slate-900 px-6 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {loading ? "Sending..." : <Send size={18} />}
          </button>
        </div>
        {error && <p className="text-sm text-red-500">{error}</p>}
      </form>
      <div className="mt-4 flex items-center justify-between rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-600 dark:bg-slate-900 dark:text-slate-300">
        <span className="inline-flex items-center gap-2">
          <Upload size={16} /> Upload can be used from the panel above.
        </span>
        <span>Dataset session: {sessionId}</span>
      </div>
    </div>
  );
}
