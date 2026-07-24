"use client";

import { Database, Sparkles } from "lucide-react";
import Sidebar from "@/components/sidebar/Sidebar";
import ChatWindow from "@/components/chat/ChatWindow";
import ChatInput from "@/components/chat/ChatInput";
import UploadDropzone from "@/components/upload/UploadDropzone";
import ResponsePanel from "@/components/response/ResponsePanel";
import { useChatStore } from "@/store/chatStore";

export default function HomePage() {
  const sessionId = useChatStore((s) => s.sessionId);
  const datasetName = useChatStore((s) => s.datasetName);
  const filePath = useChatStore((s) => s.filePath);
  const shortSession = sessionId?.replace(/^session-/, "").slice(-6) || "—";

  return (
    <main className="h-screen overflow-hidden bg-[#f4f6f9] text-slate-900">
      <div className="mx-auto flex h-full max-w-[1680px] flex-col gap-3 p-3 md:gap-4 md:p-4">
        {/* Top bar */}
        <header className="surface flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-soft">
              <Sparkles size={18} strokeWidth={2.2} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-base font-semibold tracking-tight text-slate-900 md:text-lg">
                  Analytics Copilot
                </h1>
                <span className="chip hidden sm:inline-flex">AI Analyst</span>
              </div>
              <p className="mt-0.5 truncate text-xs text-slate-500">
                Ask any topic · open data · your files · charts & forecasts
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="chip" title={sessionId}>
              Session · {shortSession}
            </span>
            <span className={datasetName || filePath ? "chip chip-success" : "chip chip-accent"}>
              <Database size={12} />
              {datasetName
                ? datasetName.length > 28
                  ? `${datasetName.slice(0, 28)}…`
                  : datasetName
                : filePath
                  ? "Uploaded file"
                  : "Open-data mode"}
            </span>
          </div>
        </header>

        {/* Workspace */}
        <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[240px_minmax(0,1fr)_360px] xl:grid-cols-[260px_minmax(0,1fr)_400px]">
          <div className="min-h-0 hidden lg:block">
            <Sidebar />
          </div>

          <section
            id="analyze-panel"
            className="surface flex min-h-0 flex-col overflow-hidden"
          >
            <div className="panel-header flex items-center justify-between gap-3">
              <div>
                <p className="label-caps text-blue-600/80">Workspace</p>
                <h2 className="text-sm font-semibold text-slate-900">Ask your data</h2>
              </div>
              <p className="hidden text-right text-[11px] text-slate-400 sm:block">
                Enter · send · Shift+Enter · new line
              </p>
            </div>

            <div className="flex min-h-0 flex-1 flex-col px-3 pb-3 pt-2 md:px-4 md:pb-4">
              <ChatWindow />
              <div className="mt-auto space-y-2.5 border-t border-slate-100 pt-3">
                <ChatInput />
                <UploadDropzone />
              </div>
            </div>
          </section>

          <div className="min-h-0 hidden lg:block">
            <ResponsePanel />
          </div>
        </div>

        <div className="min-h-[300px] lg:hidden">
          <ResponsePanel />
        </div>
      </div>
    </main>
  );
}
