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
  const discovery = active?.discovery;
  const hasContent =
    Boolean(answer) ||
    Boolean(displayCharts?.length) ||
    Boolean(displayForecast) ||
    Boolean(displayHypotheses?.length) ||
    Boolean(displaySuggestions?.length);

  return (
    <aside className="surface flex h-full w-full flex-col overflow-hidden">
      <div className="panel-header">
        <p className="label-caps text-violet-600/80">Insights</p>
        <h2 className="text-sm font-semibold text-slate-900">Analysis output</h2>
        <p className="mt-0.5 truncate text-[11px] text-slate-400">
          {datasetName ? `Working set · ${datasetName}` : "Charts, forecasts & next steps"}
        </p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3 scrollbar-thin md:p-4">
        {loading && !active ? (
          <div className="flex h-36 flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50/70">
            <div className="flex items-center gap-1">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-violet-500" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-violet-500" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-violet-500" />
            </div>
            <p className="mt-3 text-sm text-slate-500">Building response…</p>
          </div>
        ) : null}

        {!loading && !hasContent ? (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 px-4 py-8 text-center">
            <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-white text-slate-400 shadow-soft ring-1 ring-slate-100">
              <Sparkles size={18} />
            </div>
            <p className="mt-3 text-sm font-medium text-slate-700">No response yet</p>
            <p className="mt-1 text-[11px] leading-5 text-slate-400">
              Ask a question in chat. Insights, charts, and forecasts will show here.
            </p>
          </div>
        ) : null}

        {discovery && discovery.status ? (
          <div
            className={`rounded-xl border px-3 py-2 text-[11px] ${
              discovery.status === "found" || discovery.status === "provided"
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-amber-200 bg-amber-50 text-amber-900"
            }`}
          >
            <span className="font-semibold capitalize">{String(discovery.status).replace("_", " ")}</span>
            {discovery.source ? ` · ${discovery.source}` : ""}
            {discovery.title ? ` · ${discovery.title}` : ""}
          </div>
        ) : null}

        {answer ? (
          <section className="surface-muted p-3.5">
            <div className="section-title mb-2">
              <Sparkles size={15} className="text-violet-500" />
              Answer
            </div>
            <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{answer}</p>
          </section>
        ) : null}

        {displayCharts?.length ? (
          <section className="space-y-2.5">
            <div className="section-title">
              <BarChart3 size={15} className="text-blue-500" />
              Charts
              <span className="ml-auto text-[11px] font-medium text-slate-400">
                {displayCharts.length}
              </span>
            </div>
            {displayCharts.map((chart) => (
              <ChartRenderer key={chart.id} chart={chart} />
            ))}
          </section>
        ) : null}

        {displayForecast ? (
          <section className="space-y-2">
            <div className="section-title">
              <LineChart size={15} className="text-emerald-500" />
              Forecast
            </div>
            <ForecastPanel forecast={displayForecast} />
          </section>
        ) : null}

        {displayHypotheses?.length ? (
          <section className="surface-muted p-3.5">
            <div className="section-title mb-2">
              <Lightbulb size={15} className="text-amber-500" />
              Hypotheses
            </div>
            <ul className="space-y-1.5">
              {displayHypotheses.map((item, index) => (
                <li
                  key={`${item}-${index}`}
                  className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-slate-700 ring-1 ring-slate-100"
                >
                  {item}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {displaySuggestions?.length ? (
          <section className="surface-muted p-3.5">
            <SuggestionsPanel suggestions={displaySuggestions} />
          </section>
        ) : null}
      </div>
    </aside>
  );
}
