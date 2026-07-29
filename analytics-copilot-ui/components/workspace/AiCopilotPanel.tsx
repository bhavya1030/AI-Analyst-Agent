"use client";

import { useMemo } from "react";
import {
  Bot,
  Lightbulb,
  MessageSquare,
  Wrench,
  X,
} from "lucide-react";
import ChatWindow from "@/components/chat/ChatWindow";
import ChatInput from "@/components/chat/ChatInput";
import UploadDropzone from "@/components/upload/UploadDropzone";
import SuggestionsPanel from "@/components/suggestions/SuggestionsPanel";
import { useChatStore } from "@/store/chatStore";

export default function AiCopilotPanel({
  mobile,
  onClose,
}: {
  mobile?: boolean;
  onClose?: () => void;
}) {
  const messages = useChatStore((s) => s.messages);
  const activeAssistantId = useChatStore((s) => s.activeAssistantId);
  const suggestions = useChatStore((s) => s.suggestions);
  const hypotheses = useChatStore((s) => s.hypotheses);
  const loading = useChatStore((s) => s.loading);

  const active = useMemo(() => {
    if (activeAssistantId) {
      return messages.find((m) => m.id === activeAssistantId && m.role === "assistant");
    }
    return [...messages].reverse().find((m) => m.role === "assistant");
  }, [messages, activeAssistantId]);

  const displaySuggestions = active?.suggestions?.length
    ? active.suggestions
    : suggestions;
  const displayHypotheses = active?.hypotheses?.length
    ? active.hypotheses
    : hypotheses;
  const source = active?.source;
  const discovery = active?.discovery;

  const tools = useMemo(() => {
    const items: string[] = [];
    if (discovery?.status) items.push(`Dataset discovery · ${discovery.status}`);
    if (active?.charts?.length) items.push(`Chart generation · ${active.charts.length}`);
    if (active?.forecast) items.push("Forecast model");
    if (displayHypotheses?.length) items.push("Hypothesis engine");
    if (source) items.push(`Source · ${source}`);
    if (loading) items.push("Pipeline running…");
    return items;
  }, [discovery, active, displayHypotheses, source, loading]);

  return (
    <aside
      className={`surface flex h-full min-h-0 flex-col overflow-hidden ${
        mobile ? "animate-slide-up" : "animate-fade-in"
      }`}
    >
      <div className="panel-header flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="label-caps text-accent">AI Copilot</p>
          <h2 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            <Bot size={15} className="text-accent" />
            Assistant
          </h2>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Chat · suggestions · reasoning · tools
          </p>
        </div>
        {mobile && onClose ? (
          <button type="button" className="btn-icon" onClick={onClose}>
            <X size={16} />
          </button>
        ) : null}
      </div>

      {/* Chat */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center gap-1.5 border-b border-border px-3 py-1.5">
          <MessageSquare size={12} className="text-muted-foreground" />
          <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Conversation
          </span>
        </div>
        <div className="min-h-0 flex-1 px-2.5 py-2 md:px-3">
          <ChatWindow />
        </div>
        <div className="space-y-2 border-t border-border px-2.5 py-2.5 md:px-3">
          <ChatInput />
          <UploadDropzone />
        </div>
      </div>

      {/* Secondary panes */}
      <div className="max-h-[38%] shrink-0 overflow-y-auto border-t border-border scrollbar-thin">
        <div className="space-y-3 p-3">
          <section>
            <div className="section-title mb-2 text-xs">
              <Lightbulb size={13} className="text-warning" />
              Suggestions
            </div>
            <SuggestionsPanel suggestions={displaySuggestions} />
          </section>

          <section>
            <div className="section-title mb-2 text-xs">
              <BrainIcon />
              Reasoning
            </div>
            {displayHypotheses?.length ? (
              <ul className="space-y-1.5">
                {displayHypotheses.slice(0, 4).map((h, i) => (
                  <li
                    key={i}
                    className="rounded-xl border border-border bg-surface-muted px-2.5 py-2 text-[11px] leading-4 text-foreground/90"
                  >
                    {h}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                Model reasoning and hypotheses appear after analysis.
              </p>
            )}
          </section>

          <section>
            <div className="section-title mb-2 text-xs">
              <Wrench size={13} className="text-accent" />
              Tool usage
            </div>
            {tools.length ? (
              <ul className="flex flex-wrap gap-1.5">
                {tools.map((t) => (
                  <li key={t} className="chip !py-0.5">
                    {t}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                Tools activate when you ask a question.
              </p>
            )}
          </section>
        </div>
      </div>
    </aside>
  );
}

function BrainIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-accent"
    >
      <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
      <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" />
      <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4" />
      <path d="M12 18v-5" />
    </svg>
  );
}
