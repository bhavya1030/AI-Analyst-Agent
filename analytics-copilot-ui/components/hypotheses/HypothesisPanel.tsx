"use client";

interface HypothesisPanelProps {
  hypotheses?: string[];
}

export default function HypothesisPanel({ hypotheses = [] }: HypothesisPanelProps) {
  return (
    <div>
      <div className="mb-3">
        <h3 className="text-lg font-semibold">Hypotheses</h3>
        <p className="text-sm text-slate-500 dark:text-slate-400">Potential insights for your dataset.</p>
      </div>
      {hypotheses.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">No hypothesis available yet.</p>
      ) : (
        <ul className="space-y-3">
          {hypotheses.map((hypothesis, index) => (
            <li key={index} className="rounded-3xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 shadow-sm dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100">
              {hypothesis}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
