"use client";

import { ForecastResult } from "@/types";
import ChartRenderer from "@/components/charts/ChartRenderer";

interface ForecastPanelProps {
  forecast: ForecastResult;
}

export default function ForecastPanel({ forecast }: ForecastPanelProps) {
  const preview = (forecast.values || []).slice(-5);

  return (
    <div className="space-y-2.5 rounded-2xl border border-slate-200/90 bg-white p-3 shadow-soft">
      {forecast.explanation ? (
        <p className="text-xs leading-5 text-slate-600">{forecast.explanation}</p>
      ) : (
        <p className="text-xs text-slate-500">Forecast results ready for review.</p>
      )}

      {forecast.chart ? (
        <ChartRenderer chart={{ id: "forecast-chart", type: "Forecast", figure: forecast.chart }} />
      ) : null}

      {preview.length ? (
        <div className="overflow-hidden rounded-xl border border-slate-100 bg-slate-50">
          <div className="border-b border-slate-100 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Latest points
          </div>
          <div className="max-h-40 overflow-auto p-2 scrollbar-thin">
            <table className="w-full text-left text-[11px] text-slate-600">
              <thead>
                <tr className="text-slate-400">
                  {Object.keys(preview[0] || {})
                    .slice(0, 4)
                    .map((key) => (
                      <th key={key} className="px-2 py-1 font-medium">
                        {key}
                      </th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {preview.map((row, i) => (
                  <tr key={i} className="border-t border-slate-100/80">
                    {Object.values(row)
                      .slice(0, 4)
                      .map((val, j) => (
                        <td key={j} className="max-w-[90px] truncate px-2 py-1">
                          {formatCell(val)}
                        </td>
                      ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function formatCell(val: unknown): string {
  if (val == null) return "—";
  if (typeof val === "number") return Number.isFinite(val) ? val.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(val);
  const s = String(val);
  return s.length > 24 ? `${s.slice(0, 24)}…` : s;
}
