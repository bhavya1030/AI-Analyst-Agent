"use client";

import { useMemo } from "react";
import { BarChart3, Lightbulb, LineChart, Sparkles } from "lucide-react";
import { useChatStore } from "@/store/chatStore";
import ChartRenderer from "@/components/charts/ChartRenderer";
import ForecastPanel from "@/components/forecast/ForecastPanel";
import SuggestionsPanel from "@/components/suggestions/SuggestionsPanel";

export default function ResponsePanel() {
  const { messages, activeAssistantId, charts, forecast, hypotheses, suggestions, datasetName, loading } =
    useChatStore();

  const active = useMemo(() => {
    if (activeAssistantId) {
      return messages.find((m) => m.id === activeAssistantId && m.role === "assistant") || null;
    }
    const assistants = messages.filter((m) => m.role === "assistant");
    return assistants[assistants.length - 1] || null;
  }, [messages, activeAssistantId]);

  const displayCharts = active?.charts?.length ? active.charts : charts;
  const displayForecast = active?.forecast || forecast;
  const displayHypotheses = active?.hypotheses?.length ? active.hypotheses : hypotheses;
  const displaySuggestions = active?.suggestions?.length ? active.suggestions : suggestions;
  const answer = active?.text || "";

  return (
    <aside className="flex h-full w-full flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-card dark:border-slate-800 dark:bg-slate-900">
      <div className="border-b border-slate-100 px-4 py-4 dark:border-slate-800">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-600">Response</p>
        <h2 className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-50">Analysis output</h2>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {datasetName ? `Working set: ${datasetName}` : "Charts, forecasts, and insights appear here"}
        </p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4 scrollbar-thin">
        {loading && !active ? (
          <div className="flex h-40 items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-950">
            Analyzing your question…
          </div>
        ) : null}

        {!loading && !active ? (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center dark:border-slate-700 dark:bg-slate-950">
            <Sparkles className="mx-auto text-slate-400" size={28} />
            <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">No response yet</p>
            <p className="mt-1 text-xs text-slate-500">
              Ask something in the chat, or upload a dataset and query it.
            </p>
          </div>
        ) : null}

        {answer ? (
          <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-950">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
              <Sparkles size={16} className="text-violet-500" />
              Answer
            </div>
            <p className="whitespace-pre-wrap text-sm leading-7 text-slate-700 dark:text-slate-200">{answer}</p>
          </section>
        ) : null}

        {displayCharts?.length ? (
          <section className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
              <BarChart3 size={16} className="text-sky-500" />
              Charts
            </div>
            {displayCharts.map((chart) => (
              <ChartRenderer key={chart.id} chart={chart} />
            ))}
          </section>
        ) : null}

        {displayForecast ? (
          <section>
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
              <LineChart size={16} className="text-emerald-500" />
              Forecast
            </div>
            <ForecastPanel forecast={displayForecast} />
          </section>
        ) : null}

        {displayHypotheses?.length ? (
          <section className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-950">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
              <Lightbulb size={16} className="text-amber-500" />
              Hypotheses
            </div>
            <ul className="space-y-2">
              {displayHypotheses.map((item, index) => (
                <li
                  key={`${item}-${index}`}
                  className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:bg-amber-950/30 dark:text-amber-100"
                >
                  {item}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {displaySuggestions?.length ? (
          <section className="rounded-2xl border border-slate-200 p-4 dark:border-slate-700">
            <SuggestionsPanel suggestions={displaySuggestions} />
          </section>
        ) : null}
      </div>
    </aside>
  );
}
