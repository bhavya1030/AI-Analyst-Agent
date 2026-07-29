"use client";

import { ArrowUpRight } from "lucide-react";
import { useChatStore } from "@/store/chatStore";

interface SuggestionsPanelProps {
  suggestions?: string[];
}

export default function SuggestionsPanel({ suggestions }: SuggestionsPanelProps) {
  const storeSuggestions = useChatStore((s) => s.suggestions);
  const items = suggestions ?? storeSuggestions;

  if (items.length === 0) {
    return <p className="text-[11px] text-muted-foreground">No suggestions yet.</p>;
  }

  return (
    <div className="space-y-1.5">
      {items.map((option) => (
        <button
          key={option}
          type="button"
          className="group flex w-full items-start gap-2 rounded-xl border border-border bg-surface px-2.5 py-2 text-left text-[11px] text-foreground/90 transition hover:border-accent/40 hover:bg-accent-soft/40"
          onClick={() => {
            window.dispatchEvent(new CustomEvent("copilot:ask", { detail: { text: option } }));
          }}
        >
          <span className="min-w-0 flex-1 leading-4">{option}</span>
          <ArrowUpRight
            size={12}
            className="mt-0.5 shrink-0 text-muted-foreground transition group-hover:text-accent"
          />
        </button>
      ))}
    </div>
  );
}
