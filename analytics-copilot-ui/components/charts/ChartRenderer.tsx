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
    return <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">Chart data unavailable.</div>;
  }

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-100">{chart.type || "Chart"}</div>
      <Plot data={figure.data ?? figure} layout={figure.layout ?? { autosize: true }} style={{ width: "100%" }} useResizeHandler />
    </div>
  );
}
