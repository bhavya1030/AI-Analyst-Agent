"use client";

import { useMemo } from "react";
import { useChatStore } from "@/store/chatStore";
import MessageBubble from "@/components/chat/MessageBubble";
import UploadDropzone from "@/components/upload/UploadDropzone";

export default function ChatWindow() {
  const { messages } = useChatStore();

  const renderedMessages = useMemo(
    () => messages.map((message) => <MessageBubble key={message.id} message={message} />),
    [messages]
  );

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4 shadow-card dark:border-slate-800 dark:bg-slate-950">
        <p className="text-sm text-slate-500 dark:text-slate-400">Upload a dataset or ask a question to begin analysis.</p>
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-hidden rounded-3xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto scrollbar-thin pr-2">
          {renderedMessages.length > 0 ? renderedMessages : <p className="text-slate-500">No conversation yet. Start by asking a question.</p>}
        </div>
      </div>

      <UploadDropzone />
    </div>
  );
}
