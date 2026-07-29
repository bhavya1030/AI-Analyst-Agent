"use client";

import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { Database, Globe2, Link2, Sparkles } from "lucide-react";
import { useChatStore } from "@/store/chatStore";
import MessageBubble from "@/components/chat/MessageBubble";

const STARTERS = [
  { label: "Analyze India's GDP", hint: "Open data" },
  { label: "Forecast GDP for next 10 years", hint: "Forecast" },
  { label: "Compare GDP of India with US", hint: "Compare" },
  { label: "Visualize GDP trend", hint: "Chart" },
];

export default function ChatWindow() {
  const { messages, loading } = useChatStore();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading]);

  const renderedMessages = useMemo(
    () => messages.map((message) => <MessageBubble key={message.id} message={message} />),
    [messages]
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex-1 space-y-3 overflow-y-auto px-0.5 py-1 scrollbar-thin">
        {renderedMessages.length === 0 ? (
          <div className="flex h-full min-h-[200px] flex-col items-center justify-center px-2 py-4 text-center animate-slide-up">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent-soft text-accent">
              <Sparkles size={20} />
            </div>
            <h2 className="mt-3 text-base font-semibold tracking-tight text-foreground md:text-lg">
              What would you like to analyze?
            </h2>
            <p className="mt-1.5 max-w-sm text-[12px] leading-5 text-muted-foreground">
              Ask in plain English. We find open data, use your files, then chart and forecast.
            </p>

            <div className="mt-4 grid w-full max-w-sm grid-cols-3 gap-1.5">
              <ValuePill icon={<Globe2 size={12} />} title="Open data" />
              <ValuePill icon={<Database size={12} />} title="Files" />
              <ValuePill icon={<Link2 size={12} />} title="URL" />
            </div>

            <div className="mt-4 grid w-full max-w-sm gap-1.5">
              {STARTERS.map((item) => (
                <StarterChip key={item.label} text={item.label} hint={item.hint} />
              ))}
            </div>
          </div>
        ) : (
          renderedMessages
        )}

        {loading ? (
          <div className="flex items-center gap-3 rounded-2xl border border-border bg-surface-muted px-3 py-2.5">
            <div className="flex items-center gap-1">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
            </div>
            <span className="text-xs text-muted-foreground">
              Analyzing… discovering data, charts & insights
            </span>
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function ValuePill({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface px-2 py-2 text-center shadow-soft">
      <div className="flex flex-col items-center gap-1 text-accent">
        {icon}
        <span className="text-[10px] font-semibold text-foreground">{title}</span>
      </div>
    </div>
  );
}

function StarterChip({ text, hint }: { text: string; hint: string }) {
  return (
    <button
      type="button"
      onClick={() => {
        window.dispatchEvent(new CustomEvent("copilot:ask", { detail: { text } }));
      }}
      className="group rounded-xl border border-border bg-surface px-3 py-2 text-left shadow-soft transition hover:border-accent/40 hover:bg-accent-soft/40"
    >
      <span className="text-[9px] font-semibold uppercase tracking-wide text-accent">{hint}</span>
      <p className="mt-0.5 text-[11px] font-medium leading-4 text-foreground/90">{text}</p>
    </button>
  );
}
