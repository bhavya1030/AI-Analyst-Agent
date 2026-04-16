"use client";

import { useEffect, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import { fetchSessions } from "@/services/api";
import { useChatStore } from "@/store/chatStore";

export default function Sidebar() {
  const { sessionId, datasetName, setSessionId, resetConversation } = useChatStore();
  const [sessions, setSessions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const loadSessions = async () => {
    setLoading(true);
    const data = await fetchSessions();
    setSessions(["default", ...data.filter((id) => id !== "default")]);
    setLoading(false);
  };

  useEffect(() => {
    loadSessions();
  }, []);

  return (
    <aside className="hidden w-80 flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-800 dark:bg-slate-900 xl:flex">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Sessions</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Switch datasets or start new analysis.</p>
        </div>
        <button
          type="button"
          onClick={() => {
            resetConversation();
            setSessionId(`session-${Date.now()}`);
          }}
          className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-700 transition hover:border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
        >
          <Plus size={18} />
        </button>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-950">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-500 dark:text-slate-400">Active dataset</p>
        <p className="mt-2 truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{datasetName || "No dataset loaded"}</p>
      </div>

      <div className="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
        <span>Session list</span>
        <button className="inline-flex items-center gap-1 text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100" onClick={loadSessions}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto scrollbar-thin pr-1">
        {loading && <p className="text-sm text-slate-500">Loading sessions...</p>}
        {!loading && sessions.length === 0 && <p className="text-sm text-slate-500">No sessions available.</p>}
        {sessions.map((session) => (
          <button
            key={session}
            type="button"
            onClick={() => {
              resetConversation();
              setSessionId(session);
            }}
            className={`flex w-full items-center justify-between rounded-2xl border px-3 py-3 text-left text-sm transition ${session === sessionId ? "border-sky-500 bg-sky-50 text-slate-900 dark:border-sky-400 dark:bg-slate-800" : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"}`}
          >
            <span>{session}</span>
            {session === sessionId && <span className="rounded-full bg-sky-500 px-2 py-0.5 text-[11px] font-semibold text-white">Active</span>}
          </button>
        ))}
      </div>
    </aside>
  );
}
