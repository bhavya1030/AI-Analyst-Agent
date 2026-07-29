"use client";

import dynamic from "next/dynamic";
import { ChartPayload } from "@/types";
import { useUiStore } from "@/store/uiStore";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface ChartRendererProps {
  chart: ChartPayload;
}

export default function ChartRenderer({ chart }: ChartRendererProps) {
  const resolvedTheme = useUiStore((s) => s.resolvedTheme);
  const figure = chart.figure;
  const isDark = resolvedTheme === "dark";

  if (!figure) {
    return (
      <div className="rounded-2xl border border-border bg-surface-muted px-3 py-4 text-sm text-muted-foreground">
        Chart data unavailable.
      </div>
    );
  }

  const fontColor = isDark ? "#cbd5e1" : "#475569";
  const gridColor = isDark ? "rgba(148,163,184,0.12)" : "rgba(148,163,184,0.25)";

  const layout = {
    ...(figure.layout ?? {}),
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    margin: { l: 48, r: 20, t: 36, b: 40, ...(figure.layout?.margin || {}) },
    font: { family: "Inter, system-ui, sans-serif", size: 11, color: fontColor },
    xaxis: {
      ...(figure.layout?.xaxis || {}),
      gridcolor: gridColor,
      zerolinecolor: gridColor,
      color: fontColor,
    },
    yaxis: {
      ...(figure.layout?.yaxis || {}),
      gridcolor: gridColor,
      zerolinecolor: gridColor,
      color: fontColor,
    },
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-surface p-3 shadow-soft transition hover:shadow-card">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold capitalize text-foreground">
          {chart.type || "Chart"}
        </p>
        {chart.columns_used?.length ? (
          <p className="truncate text-[10px] text-muted-foreground">
            {chart.columns_used.slice(0, 3).join(" · ")}
          </p>
        ) : null}
      </div>
      <Plot
        data={figure.data ?? figure}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%", minHeight: 260 }}
        useResizeHandler
      />
    </div>
  );
}
