"use client";

import { ArrowUpRight } from "lucide-react";
import { useChatStore } from "@/store/chatStore";

interface SuggestionsPanelProps {
  suggestions?: string[];
}

export default function SuggestionsPanel({ suggestions }: SuggestionsPanelProps) {
  const storeSuggestions = useChatStore((s) => s.suggestions);
  const items = suggestions ?? storeSuggestions;

  return (
    <div>
      <div className="mb-2.5">
        <h3 className="text-sm font-semibold text-slate-800">Suggested next</h3>
        <p className="text-[11px] text-slate-400">Click to send into chat</p>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-slate-400">No suggestions yet.</p>
      ) : (
        <div className="space-y-1.5">
          {items.map((option) => (
            <button
              key={option}
              type="button"
              className="group flex w-full items-start gap-2 rounded-xl border border-slate-200/80 bg-white px-3 py-2.5 text-left text-xs text-slate-700 transition hover:border-blue-300 hover:bg-blue-50/40"
              onClick={() => {
                window.dispatchEvent(new CustomEvent("copilot:ask", { detail: { text: option } }));
              }}
            >
              <span className="min-w-0 flex-1 leading-5">{option}</span>
              <ArrowUpRight
                size={14}
                className="mt-0.5 shrink-0 text-slate-300 transition group-hover:text-blue-500"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
