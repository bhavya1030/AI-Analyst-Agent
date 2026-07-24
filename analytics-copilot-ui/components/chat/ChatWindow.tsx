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
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const renderedMessages = useMemo(
    () => messages.map((message) => <MessageBubble key={message.id} message={message} />),
    [messages]
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex-1 space-y-3.5 overflow-y-auto px-0.5 py-1 scrollbar-thin md:px-1">
        {renderedMessages.length === 0 ? (
          <div className="flex h-full min-h-[260px] flex-col items-center justify-center px-3 py-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
              <Sparkles size={22} />
            </div>
            <h2 className="mt-4 text-xl font-semibold tracking-tight text-slate-900 md:text-2xl">
              What would you like to analyze?
            </h2>
            <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
              Ask in plain English. We’ll find open data when we can, use your files, or connect a
              source — then analyze, chart, and forecast.
            </p>

            <div className="mt-5 grid w-full max-w-lg grid-cols-1 gap-2 sm:grid-cols-3">
              <ValuePill icon={<Globe2 size={14} />} title="Open data" desc="Ask any public topic" />
              <ValuePill icon={<Database size={14} />} title="Your files" desc="CSV · Excel · JSON" />
              <ValuePill icon={<Link2 size={14} />} title="Connect URL" desc="Paste a raw file link" />
            </div>

            <div className="mt-6 grid w-full max-w-xl gap-2 sm:grid-cols-2">
              {STARTERS.map((item) => (
                <StarterChip key={item.label} text={item.label} hint={item.hint} />
              ))}
            </div>
          </div>
        ) : (
          renderedMessages
        )}

        {loading ? (
          <div className="flex items-center gap-3 rounded-2xl border border-slate-100 bg-slate-50/80 px-3.5 py-3">
            <div className="flex items-center gap-1">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-blue-500" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-blue-500" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-blue-500" />
            </div>
            <span className="text-sm text-slate-500">Analyzing… discovering data, charts & insights</span>
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function ValuePill({
  icon,
  title,
  desc,
}: {
  icon: ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200/90 bg-white px-3 py-2.5 text-left shadow-soft">
      <div className="flex items-center gap-1.5 text-blue-600">{icon}<span className="text-xs font-semibold text-slate-800">{title}</span></div>
      <p className="mt-0.5 text-[11px] text-slate-500">{desc}</p>
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
      className="group rounded-2xl border border-slate-200 bg-white px-3.5 py-3 text-left shadow-soft transition hover:border-blue-300 hover:bg-blue-50/50 hover:shadow-card"
    >
      <span className="text-[10px] font-semibold uppercase tracking-wide text-blue-600/80">{hint}</span>
      <p className="mt-1 text-xs font-medium leading-5 text-slate-700 group-hover:text-slate-900">{text}</p>
    </button>
  );
}
