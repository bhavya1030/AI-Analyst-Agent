"use client";

import { useEffect, useMemo, useRef } from "react";
import { useChatStore } from "@/store/chatStore";
import MessageBubble from "@/components/chat/MessageBubble";

const STARTERS = [
  "Analyze India's GDP",
  "Forecast GDP for next 10 years",
  "Compare GDP of India with US and plot graph",
  "Visualize GDP trend",
];

export default function ChatWindow() {
  const { messages, loading } = useChatStore();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const renderedMessages = useMemo(
    () => messages.map((message) => <MessageBubble key={message.id} message={message} />),
    [messages]
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex-1 space-y-4 overflow-y-auto px-1 py-2 scrollbar-thin">
        {renderedMessages.length === 0 ? (
          <div className="flex h-full min-h-[280px] flex-col items-center justify-center px-4 text-center">
            <div className="rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-700 dark:bg-sky-950 dark:text-sky-200">
              Analytics Copilot
            </div>
            <h2 className="mt-4 text-2xl font-semibold text-slate-900 dark:text-slate-50">
              What would you like to analyze?
            </h2>
            <p className="mt-2 max-w-md text-sm text-slate-500 dark:text-slate-400">
              Ask in plain English. Upload a CSV below or let the agent discover open datasets automatically.
            </p>
            <div className="mt-6 grid w-full max-w-xl gap-2 sm:grid-cols-2">
              {STARTERS.map((text) => (
                <StarterChip key={text} text={text} />
              ))}
            </div>
          </div>
        ) : (
          renderedMessages
        )}

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-sky-500" />
            Copilot is thinking…
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function StarterChip({ text }: { text: string }) {
  // Lazy import path via store + same send path as ChatInput would be ideal;
  // chips dispatch a custom event consumed by ChatInput to avoid circular deps.
  return (
    <button
      type="button"
      onClick={() => {
        window.dispatchEvent(new CustomEvent("copilot:ask", { detail: { text } }));
      }}
      className="rounded-2xl border border-slate-200 bg-white px-3 py-3 text-left text-xs font-medium text-slate-700 shadow-sm transition hover:border-sky-300 hover:bg-sky-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:border-sky-700"
    >
      {text}
    </button>
  );
}
