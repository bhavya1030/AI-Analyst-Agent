"use client";

import { ForecastResult } from "@/types";
import ChartRenderer from "@/components/charts/ChartRenderer";

interface ForecastPanelProps {
  forecast: ForecastResult;
}

export default function ForecastPanel({ forecast }: ForecastPanelProps) {
  const preview = (forecast.values || []).slice(-5);

  return (
    <div className="space-y-2.5 rounded-2xl border border-border bg-surface p-3 shadow-soft">
      {forecast.explanation ? (
        <p className="text-xs leading-5 text-muted-foreground">{forecast.explanation}</p>
      ) : (
        <p className="text-xs text-muted-foreground">Forecast results ready for review.</p>
      )}

      {forecast.chart ? (
        <ChartRenderer
          chart={{ id: "forecast-chart", type: "Forecast", figure: forecast.chart }}
        />
      ) : null}

      {preview.length ? (
        <div className="overflow-hidden rounded-xl border border-border bg-surface-muted">
          <div className="border-b border-border px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Latest points
          </div>
          <div className="max-h-40 overflow-auto p-2 scrollbar-thin">
            <table className="w-full text-left text-[11px] text-foreground/90">
              <thead>
                <tr className="text-muted-foreground">
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
                  <tr key={i} className="border-t border-border/70">
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
  if (typeof val === "number") return Number.isFinite(val) ? String(val) : "—";
  if (typeof val === "object") return JSON.stringify(val);
  return String(val);
}
