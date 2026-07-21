"use client";

import Sidebar from "@/components/sidebar/Sidebar";
import ChatWindow from "@/components/chat/ChatWindow";
import ChatInput from "@/components/chat/ChatInput";
import UploadDropzone from "@/components/upload/UploadDropzone";
import ResponsePanel from "@/components/response/ResponsePanel";
import { useChatStore } from "@/store/chatStore";

export default function HomePage() {
  const sessionId = useChatStore((s) => s.sessionId);
  const datasetName = useChatStore((s) => s.datasetName);

  return (
    <main className="h-screen overflow-hidden bg-gradient-to-br from-slate-100 via-slate-50 to-sky-50 text-slate-900 dark:from-slate-950 dark:via-slate-950 dark:to-slate-900 dark:text-slate-100">
      <div className="mx-auto flex h-full max-w-[1800px] flex-col gap-3 p-3 md:p-4">
        {/* Top bar */}
        <header className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-slate-200/80 bg-white/90 px-4 py-3 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Analytics Copilot</h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              ChatGPT-style data analyst — ask questions, auto-discover or upload data
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full bg-slate-100 px-3 py-1 font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              Session: {sessionId}
            </span>
            <span className="rounded-full bg-emerald-50 px-3 py-1 font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
              {datasetName ? `Data: ${datasetName}` : "Data: auto-discover"}
            </span>
          </div>
        </header>

        {/* 3-column workspace */}
        <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[260px_minmax(0,1fr)_340px] xl:grid-cols-[280px_minmax(0,1fr)_380px]">
          {/* LEFT — history */}
          <div className="min-h-0 hidden lg:block">
            <Sidebar />
          </div>

          {/* CENTER — Analyze / chat */}
          <section
            id="analyze-panel"
            className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-card dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="border-b border-slate-100 px-4 py-3 dark:border-slate-800">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-600">Analyze</p>
              <h2 className="text-base font-semibold text-slate-900 dark:text-slate-50">
                Ask your data
              </h2>
            </div>

            <div className="flex min-h-0 flex-1 flex-col px-4 pb-4 pt-3">
              <ChatWindow />
              <div className="mt-auto space-y-3 pt-2">
                <ChatInput />
                {/* BOTTOM — dataset drag & drop */}
                <UploadDropzone />
              </div>
            </div>
          </section>

          {/* RIGHT — response */}
          <div className="min-h-0 hidden lg:block">
            <ResponsePanel />
          </div>
        </div>

        {/* Mobile: stack response under chat */}
        <div className="min-h-[320px] lg:hidden">
          <ResponsePanel />
        </div>
      </div>
    </main>
  );
}
