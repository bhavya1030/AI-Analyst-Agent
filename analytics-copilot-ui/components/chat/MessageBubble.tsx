"use client";

import { Bot, Upload, Link2, Database, User } from "lucide-react";
import { ChatMessage } from "@/types";
import { useChatStore } from "@/store/chatStore";

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isAssistant = message.role === "assistant";
  const setActiveAssistantId = useChatStore((s) => s.setActiveAssistantId);
  const activeAssistantId = useChatStore((s) => s.activeAssistantId);
  const isActive = isAssistant && activeAssistantId === message.id;

  return (
    <div className={`flex gap-2.5 ${isAssistant ? "justify-start" : "justify-end"}`}>
      {isAssistant ? (
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600 ring-1 ring-slate-200/80">
          <Bot size={15} />
        </div>
      ) : null}

      <div className={`max-w-[88%] space-y-2 ${isAssistant ? "" : ""}`}>
        <button
          type="button"
          onClick={() => {
            if (isAssistant) setActiveAssistantId(message.id);
          }}
          className={`w-full rounded-2xl px-3.5 py-2.5 text-left transition ${
            isAssistant
              ? `border bg-white text-slate-800 shadow-soft ${
                  isActive
                    ? "border-blue-300 ring-2 ring-blue-50"
                    : "border-slate-200/90 hover:border-slate-300"
                }`
              : "bg-blue-600 text-white shadow-soft"
          }`}
        >
          <p className="whitespace-pre-wrap text-sm leading-6">{message.text}</p>
          {isAssistant && (message.charts?.length || message.forecast) ? (
            <p className="mt-2 text-[11px] font-medium text-blue-600">
              Charts & details on the right →
            </p>
          ) : null}
          {isAssistant && message.source ? (
            <p className="mt-1.5 text-[11px] text-slate-400">Source · {message.source}</p>
          ) : null}
        </button>

        {isAssistant && message.needsUserData && message.acquisitionOptions?.length ? (
          <div className="rounded-2xl border border-amber-200/80 bg-amber-50/70 p-3">
            <p className="text-xs font-semibold text-amber-900">Continue with your data</p>
            <ul className="mt-2 space-y-1.5">
              {message.acquisitionOptions.slice(0, 3).map((opt) => (
                <li
                  key={opt.type || opt.label}
                  className="flex items-start gap-2 text-[11px] leading-4 text-amber-950/80"
                >
                  <span className="mt-0.5 text-amber-700">
                    {opt.type === "upload" ? (
                      <Upload size={12} />
                    ) : opt.type === "direct_url" ? (
                      <Link2 size={12} />
                    ) : (
                      <Database size={12} />
                    )}
                  </span>
                  <span>
                    <span className="font-medium">{opt.label}</span>
                    {opt.how ? <span className="text-amber-900/60"> — {opt.how}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {!isAssistant ? (
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-700 ring-1 ring-blue-100">
          <User size={15} />
        </div>
      ) : null}
    </div>
  );
}
