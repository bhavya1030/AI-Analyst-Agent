"use client";

import dynamic from "next/dynamic";
import { ChartPayload } from "@/types";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface ChartRendererProps {
  chart: ChartPayload;
}

export default function ChartRenderer({ chart }: ChartRendererProps) {
  const figure = chart.figure;

  if (!figure) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-4 text-sm text-slate-500">
        Chart data unavailable.
      </div>
    );
  }

  const layout = {
    ...(figure.layout ?? {}),
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    margin: { l: 48, r: 20, t: 36, b: 40, ...(figure.layout?.margin || {}) },
    font: { family: "Inter, system-ui, sans-serif", size: 11, color: "#475569" },
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white p-3 shadow-soft">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold capitalize text-slate-700">
          {chart.type || "Chart"}
        </p>
        {chart.columns_used?.length ? (
          <p className="truncate text-[10px] text-slate-400">
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
