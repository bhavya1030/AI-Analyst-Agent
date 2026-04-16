"use client";

import { ForecastResult } from "@/types";
import ChartRenderer from "@/components/charts/ChartRenderer";

interface ForecastPanelProps {
  forecast: ForecastResult;
}

export default function ForecastPanel({ forecast }: ForecastPanelProps) {
  return (
    <div className="mt-4 rounded-3xl border border-slate-200 bg-slate-50 p-4 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="mb-3 flex items-center justify-between text-sm font-semibold text-slate-900 dark:text-slate-100">
        <span>Forecast Summary</span>
      </div>
      <div className="space-y-3 text-sm text-slate-700 dark:text-slate-200">
        {forecast.explanation ? <p>{forecast.explanation}</p> : <p>Forecast results are available for review.</p>}
        {forecast.chart ? (
          <div className="mt-3">
            <ChartRenderer chart={{ id: "forecast-chart", type: "Forecast", figure: forecast.chart }} />
          </div>
        ) : null}
        <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white p-3 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
          <pre className="max-h-52 overflow-auto">{JSON.stringify(forecast.values.slice(-5), null, 2)}</pre>
        </div>
      </div>
    </div>
  );
}
