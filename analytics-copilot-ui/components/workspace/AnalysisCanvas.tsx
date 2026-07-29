"use client";

import { useMemo } from "react";
import {
  BarChart3,
  Brain,
  FileText,
  Lightbulb,
  LineChart,
  Sparkles,
  Table2,
} from "lucide-react";
import { useChatStore } from "@/store/chatStore";
import { useUiStore, type AnalysisTab } from "@/store/uiStore";
import ChartRenderer from "@/components/charts/ChartRenderer";
import ForecastPanel from "@/components/forecast/ForecastPanel";

const TABS: { id: AnalysisTab; label: string; icon: typeof BarChart3 }[] = [
  { id: "overview", label: "Overview", icon: Sparkles },
  { id: "charts", label: "Charts", icon: BarChart3 },
  { id: "eda", label: "EDA", icon: Brain },
  { id: "forecast", label: "Forecast", icon: LineChart },
  { id: "insights", label: "Insights", icon: Lightbulb },
  { id: "tables", label: "Tables", icon: Table2 },
  { id: "reports", label: "Reports", icon: FileText },
];

export default function AnalysisCanvas() {
  const {
    messages,
    activeAssistantId,
    charts,
    forecast,
    hypotheses,
    suggestions,
    datasetName,
    loading,
  } = useChatStore();
  const analysisTab = useUiStore((s) => s.analysisTab);
  const setAnalysisTab = useUiStore((s) => s.setAnalysisTab);
  const workspaceId = useUiStore((s) => s.workspaceId);

  const active = useMemo(() => {
    if (activeAssistantId) {
      return (
        messages.find((m) => m.id === activeAssistantId && m.role === "assistant") ||
        null
      );
    }
    const assistants = messages.filter((m) => m.role === "assistant");
    return assistants[assistants.length - 1] || null;
  }, [messages, activeAssistantId]);

  const displayCharts = active?.charts?.length ? active.charts : charts;
  const displayForecast = active?.forecast || forecast;
  const displayHypotheses = active?.hypotheses?.length
    ? active.hypotheses
    : hypotheses;
  const displaySuggestions = active?.suggestions?.length
    ? active.suggestions
    : suggestions;
  const answer = active?.text || "";
  const discovery = active?.discovery;
  const related = active?.relatedDatasets || [];
  const source = active?.source || "";

  const tableRows = useMemo(() => {
    const values = displayForecast?.values || [];
    if (values.length) return values;
    return [];
  }, [displayForecast]);

  const hasContent =
    Boolean(answer) ||
    Boolean(displayCharts?.length) ||
    Boolean(displayForecast) ||
    Boolean(displayHypotheses?.length);

  return (
    <section className="surface flex h-full min-h-0 flex-col overflow-hidden animate-fade-in">
      <div className="panel-header flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-caps text-accent">Analysis canvas</p>
          <h2 className="text-sm font-semibold text-foreground">
            {workspaceId === "forecasting"
              ? "Forecast workspace"
              : workspaceId === "research"
                ? "Research workspace"
                : "Insights & visuals"}
          </h2>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
            {datasetName
              ? `Working set · ${datasetName}`
              : "Charts · EDA · forecasts · tables · reports"}
          </p>
        </div>
        {loading ? (
          <span className="chip chip-accent animate-pulse-soft">Analyzing…</span>
        ) : hasContent ? (
          <span className="chip chip-success">Results ready</span>
        ) : (
          <span className="chip">Waiting for analysis</span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 overflow-x-auto border-b border-border px-2 py-2 scrollbar-thin md:px-3">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const activeTab = analysisTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setAnalysisTab(tab.id)}
              className={`tab-btn ${activeTab ? "tab-btn-active" : "tab-btn-idle"}`}
            >
              <Icon size={13} />
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3 scrollbar-thin md:p-4">
        {loading && !hasContent ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="skeleton h-40" />
            <div className="skeleton h-40" />
            <div className="skeleton h-28 sm:col-span-2" />
          </div>
        ) : null}

        {!loading && !hasContent ? (
          <div className="empty-state animate-slide-up">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
              <BarChart3 size={22} />
            </div>
            <p className="mt-4 text-sm font-semibold text-foreground">
              Your analysis will appear here
            </p>
            <p className="mt-1.5 max-w-md text-[12px] leading-5 text-muted-foreground">
              Use the AI assistant on the right to ask questions. Charts, EDA
              summaries, forecasts, and structured insights render in this canvas.
            </p>
          </div>
        ) : null}

        {(analysisTab === "overview" || analysisTab === "insights") && hasContent ? (
          <div className="space-y-3 animate-slide-up">
            {discovery && discovery.status ? (
              <div
                className={`rounded-xl border px-3 py-2 text-[11px] ${
                  discovery.status === "found" || discovery.status === "provided"
                    ? "border-success/30 bg-success-soft text-success"
                    : "border-warning/30 bg-warning-soft text-warning"
                }`}
              >
                <span className="font-semibold capitalize">
                  {String(discovery.status).replace(/_/g, " ")}
                </span>
                {discovery.source ? ` · ${discovery.source}` : ""}
                {discovery.title ? ` · ${discovery.title}` : ""}
              </div>
            ) : null}

            {answer ? (
              <section className="surface-muted p-4">
                <div className="section-title mb-2">
                  <Sparkles size={15} className="text-accent" />
                  Executive insight
                </div>
                <p className="whitespace-pre-wrap text-sm leading-6 text-foreground/90">
                  {answer}
                </p>
                {source ? (
                  <p className="mt-2 text-[11px] text-muted-foreground">Source · {source}</p>
                ) : null}
              </section>
            ) : null}

            {analysisTab === "overview" && displayCharts?.length ? (
              <section className="space-y-2.5">
                <div className="section-title">
                  <BarChart3 size={15} className="text-accent" />
                  Key charts
                </div>
                <div className="grid gap-3 xl:grid-cols-2">
                  {displayCharts.slice(0, 2).map((chart) => (
                    <ChartRenderer key={chart.id} chart={chart} />
                  ))}
                </div>
              </section>
            ) : null}

            {analysisTab === "overview" && displayForecast ? (
              <section className="space-y-2">
                <div className="section-title">
                  <LineChart size={15} className="text-success" />
                  Forecast preview
                </div>
                <ForecastPanel forecast={displayForecast} />
              </section>
            ) : null}

            {displayHypotheses?.length ? (
              <section className="surface-muted p-4">
                <div className="section-title mb-2">
                  <Lightbulb size={15} className="text-warning" />
                  Hypotheses & reasoning
                </div>
                <ul className="space-y-1.5">
                  {displayHypotheses.map((item, index) => (
                    <li
                      key={`${item}-${index}`}
                      className="rounded-xl border border-border bg-surface px-3 py-2 text-xs leading-5 text-foreground/90"
                    >
                      {item}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {related.length ? (
              <section className="surface-muted p-4">
                <div className="section-title mb-2">Related datasets</div>
                <ul className="space-y-1 text-[11px] text-muted-foreground">
                  {related.slice(0, 5).map((r, i) => (
                    <li key={i} className="truncate">
                      {String((r as any).title || (r as any).name || JSON.stringify(r))}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </div>
        ) : null}

        {analysisTab === "charts" ? (
          <div className="space-y-3 animate-slide-up">
            {displayCharts?.length ? (
              <div className="grid gap-3 xl:grid-cols-2">
                {displayCharts.map((chart) => (
                  <ChartRenderer key={chart.id} chart={chart} />
                ))}
              </div>
            ) : (
              <EmptyTab label="No charts yet" hint="Ask for a visualization or correlation plot." />
            )}
          </div>
        ) : null}

        {analysisTab === "eda" ? (
          <div className="space-y-3 animate-slide-up">
            {answer || displayHypotheses?.length ? (
              <>
                <section className="surface-muted p-4">
                  <div className="section-title mb-2">
                    <Brain size={15} className="text-accent" />
                    Exploratory summary
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-foreground/90">
                    {answer || "EDA findings will appear after analysis."}
                  </p>
                </section>
                {displayCharts?.length ? (
                  <div className="grid gap-3">
                    {displayCharts.map((chart) => (
                      <ChartRenderer key={chart.id} chart={chart} />
                    ))}
                  </div>
                ) : null}
              </>
            ) : (
              <EmptyTab
                label="No EDA results"
                hint="Try “profile this dataset” or “summarize distributions”."
              />
            )}
          </div>
        ) : null}

        {analysisTab === "forecast" ? (
          <div className="space-y-3 animate-slide-up">
            {displayForecast ? (
              <ForecastPanel forecast={displayForecast} />
            ) : (
              <EmptyTab
                label="No forecast yet"
                hint="Ask to predict the next N periods for a metric."
              />
            )}
          </div>
        ) : null}

        {analysisTab === "tables" ? (
          <div className="animate-slide-up">
            {tableRows.length ? (
              <div className="overflow-hidden rounded-2xl border border-border bg-surface">
                <div className="border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Forecast / result table
                </div>
                <div className="max-h-[480px] overflow-auto scrollbar-thin">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-surface-muted">
                      <tr className="text-muted-foreground">
                        {Object.keys(tableRows[0] || {})
                          .slice(0, 8)
                          .map((key) => (
                            <th key={key} className="px-3 py-2 font-semibold">
                              {key}
                            </th>
                          ))}
                      </tr>
                    </thead>
                    <tbody>
                      {tableRows.map((row, i) => (
                        <tr key={i} className="border-t border-border/70">
                          {Object.values(row)
                            .slice(0, 8)
                            .map((val, j) => (
                              <td key={j} className="max-w-[140px] truncate px-3 py-1.5 text-foreground/90">
                                {formatCell(val)}
                              </td>
                            ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <EmptyTab
                label="No tabular data"
                hint="Forecast values and structured result tables show here."
              />
            )}
          </div>
        ) : null}

        {analysisTab === "reports" ? (
          <div className="space-y-3 animate-slide-up">
            {hasContent ? (
              <section className="surface-muted p-4">
                <div className="section-title mb-3">
                  <FileText size={15} className="text-accent" />
                  Analysis report
                </div>
                <div className="space-y-3 text-sm leading-6 text-foreground/90">
                  <p>
                    <span className="font-semibold">Dataset: </span>
                    {datasetName || "Open-data / unspecified"}
                  </p>
                  {answer ? (
                    <div>
                      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Findings
                      </p>
                      <p className="whitespace-pre-wrap">{answer}</p>
                    </div>
                  ) : null}
                  {displayHypotheses?.length ? (
                    <div>
                      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Hypotheses
                      </p>
                      <ol className="list-decimal space-y-1 pl-4 text-xs">
                        {displayHypotheses.map((h, i) => (
                          <li key={i}>{h}</li>
                        ))}
                      </ol>
                    </div>
                  ) : null}
                  {displaySuggestions?.length ? (
                    <div>
                      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Recommended next steps
                      </p>
                      <ul className="list-disc space-y-1 pl-4 text-xs">
                        {displaySuggestions.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  <p className="text-[11px] text-muted-foreground">
                    Charts: {displayCharts?.length || 0} · Forecast:{" "}
                    {displayForecast ? "yes" : "no"} · Generated in this session
                  </p>
                </div>
              </section>
            ) : (
              <EmptyTab
                label="No report yet"
                hint="Complete an analysis to generate a structured report draft."
              />
            )}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function EmptyTab({ label, hint }: { label: string; hint: string }) {
  return (
    <div className="empty-state">
      <p className="text-sm font-semibold text-foreground">{label}</p>
      <p className="mt-1 max-w-sm text-[12px] text-muted-foreground">{hint}</p>
    </div>
  );
}

function formatCell(val: unknown): string {
  if (val == null) return "—";
  if (typeof val === "number") return Number.isFinite(val) ? String(val) : "—";
  if (typeof val === "object") return JSON.stringify(val);
  return String(val);
}
