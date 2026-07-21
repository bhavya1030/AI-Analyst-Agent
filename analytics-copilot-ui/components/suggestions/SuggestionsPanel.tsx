"use client";

import { useChatStore } from "@/store/chatStore";

interface SuggestionsPanelProps {
  suggestions?: string[];
}

export default function SuggestionsPanel({ suggestions }: SuggestionsPanelProps) {
  const storeSuggestions = useChatStore((s) => s.suggestions);
  const items = suggestions ?? storeSuggestions;

  return (
    <div>
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Suggested next questions</h3>
        <p className="text-xs text-slate-500">Click to send into chat</p>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-slate-500">No suggestions yet.</p>
      ) : (
        <div className="space-y-2">
          {items.map((option) => (
            <button
              key={option}
              type="button"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-left text-xs text-slate-700 transition hover:border-sky-300 hover:bg-sky-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:border-sky-700"
              onClick={() => {
                window.dispatchEvent(new CustomEvent("copilot:ask", { detail: { text: option } }));
              }}
            >
              {option}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
