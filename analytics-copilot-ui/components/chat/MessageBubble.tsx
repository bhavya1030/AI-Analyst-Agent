"use client";

import { Bot, User } from "lucide-react";
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
    <div className={`flex gap-3 ${isAssistant ? "justify-start" : "justify-end"}`}>
      {isAssistant ? (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-200">
          <Bot size={16} />
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => {
          if (isAssistant) setActiveAssistantId(message.id);
        }}
        className={`max-w-[85%] rounded-3xl px-4 py-3 text-left shadow-sm transition ${
          isAssistant
            ? `border bg-white text-slate-800 dark:bg-slate-950 dark:text-slate-100 ${
                isActive
                  ? "border-violet-400 ring-2 ring-violet-100 dark:ring-violet-900"
                  : "border-slate-200 dark:border-slate-800"
              }`
            : "border border-sky-600 bg-sky-600 text-white"
        }`}
      >
        <p className="whitespace-pre-wrap text-sm leading-6">{message.text}</p>
        {isAssistant && (message.charts?.length || message.forecast) ? (
          <p className="mt-2 text-[11px] font-medium text-violet-600 dark:text-violet-300">
            Click to focus charts & details on the right →
          </p>
        ) : null}
      </button>

      {!isAssistant ? (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-200">
          <User size={16} />
        </div>
      ) : null}
    </div>
  );
}
