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
    <div className={`flex gap-2 ${isAssistant ? "justify-start" : "justify-end"}`}>
      {isAssistant ? (
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-muted text-muted-foreground ring-1 ring-border">
          <Bot size={13} />
        </div>
      ) : null}

      <div className="max-w-[90%] space-y-2">
        <button
          type="button"
          onClick={() => {
            if (isAssistant) setActiveAssistantId(message.id);
          }}
          className={`w-full rounded-2xl px-3 py-2 text-left transition ${
            isAssistant
              ? `border bg-surface text-foreground shadow-soft ${
                  isActive
                    ? "border-accent ring-2 ring-accent/15"
                    : "border-border hover:border-accent/30"
                }`
              : "bg-accent text-accent-foreground shadow-soft"
          }`}
        >
          <p className="whitespace-pre-wrap text-[13px] leading-5">{message.text}</p>
          {isAssistant && (message.charts?.length || message.forecast) ? (
            <p className="mt-1.5 text-[10px] font-medium text-accent">
              Charts & details in analysis canvas ←
            </p>
          ) : null}
          {isAssistant && message.source ? (
            <p className="mt-1 text-[10px] text-muted-foreground">Source · {message.source}</p>
          ) : null}
        </button>

        {isAssistant && message.needsUserData && message.acquisitionOptions?.length ? (
          <div className="rounded-2xl border border-warning/30 bg-warning-soft p-2.5">
            <p className="text-[11px] font-semibold text-warning">Continue with your data</p>
            <ul className="mt-1.5 space-y-1">
              {message.acquisitionOptions.slice(0, 3).map((opt) => (
                <li
                  key={opt.type || opt.label}
                  className="flex items-start gap-2 text-[10px] leading-4 text-foreground/80"
                >
                  <span className="mt-0.5 text-warning">
                    {opt.type === "upload" ? (
                      <Upload size={11} />
                    ) : opt.type === "direct_url" ? (
                      <Link2 size={11} />
                    ) : (
                      <Database size={11} />
                    )}
                  </span>
                  <span>
                    <span className="font-medium">{opt.label}</span>
                    {opt.how ? (
                      <span className="text-muted-foreground"> — {opt.how}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {!isAssistant ? (
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent ring-1 ring-accent/20">
          <User size={13} />
        </div>
      ) : null}
    </div>
  );
}
