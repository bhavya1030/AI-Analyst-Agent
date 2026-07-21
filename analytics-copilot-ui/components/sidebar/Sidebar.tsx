"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronRight, MessageSquarePlus, RefreshCw } from "lucide-react";
import { fetchSessionDetail, fetchSessions } from "@/services/api";
import { useChatStore } from "@/store/chatStore";

type SessionRow = {
  id: string;
  title: string;
  subtitle: string;
  timestamp: number;
  focusMessageId?: string;
};

export default function Sidebar() {
  const {
    sessionId,
    datasetName,
    history,
    sessionsById,
    openSession,
    startNewChat,
    saveCurrentSession,
  } = useChatStore();

  const [remoteSessions, setRemoteSessions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [openingId, setOpeningId] = useState<string | null>(null);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const data = await fetchSessions();
      setRemoteSessions(data || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadSessions();
  }, []);

  /** Previous sessions only — never the active chat */
  const previousSessions = useMemo(() => {
    const rows = new Map<string, SessionRow>();

    // Local history (user questions), excluding current session
    for (const item of history) {
      if (!item.sessionId || item.sessionId === sessionId) continue;
      const existing = rows.get(item.sessionId);
      if (!existing || item.timestamp >= existing.timestamp) {
        rows.set(item.sessionId, {
          id: item.sessionId,
          title: item.title || item.preview || item.sessionId,
          subtitle: item.datasetName || "Previous session",
          timestamp: item.timestamp,
          focusMessageId: item.messageId,
        });
      }
    }

    // Cached snapshots
    for (const [id, snap] of Object.entries(sessionsById || {})) {
      if (!id || id === sessionId) continue;
      const firstUser = [...(snap.messages || [])].reverse().find((m) => m.role === "user");
      const title = firstUser?.text?.slice(0, 72) || snap.datasetName || id;
      const existing = rows.get(id);
      if (!existing || (snap.updatedAt || 0) >= existing.timestamp) {
        rows.set(id, {
          id,
          title,
          subtitle: snap.datasetName || existing?.subtitle || "Saved session",
          timestamp: snap.updatedAt || existing?.timestamp || Date.now(),
          focusMessageId: existing?.focusMessageId,
        });
      }
    }

    // Remote backend sessions
    for (const id of remoteSessions) {
      if (!id || id === sessionId || rows.has(id)) continue;
      // Skip noisy system/test ids only if empty of value? Keep all except current.
      rows.set(id, {
        id,
        title: id,
        subtitle: "Server session",
        timestamp: 0,
      });
    }

    return Array.from(rows.values()).sort((a, b) => b.timestamp - a.timestamp);
  }, [history, sessionsById, remoteSessions, sessionId]);

  const openSessionInAnalyze = async (targetSessionId: string, focusMessageId?: string) => {
    if (!targetSessionId || targetSessionId === sessionId) return;
    setOpeningId(targetSessionId);
    try {
      saveCurrentSession();
      const cached = sessionsById[targetSessionId];
      if (cached?.messages?.length) {
        openSession(targetSessionId, { focusMessageId });
        return;
      }
      const detail = await fetchSessionDetail(targetSessionId);
      if (detail) {
        openSession(targetSessionId, { focusMessageId, detail });
      } else {
        openSession(targetSessionId, { focusMessageId });
      }
    } finally {
      setOpeningId(null);
      document.getElementById("analyze-panel")?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  };

  return (
    <aside className="flex h-full w-full flex-col overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-card dark:border-slate-800 dark:bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-4 dark:border-slate-800">
        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-50">History</h2>
          <p className="mt-0.5 text-xs text-slate-500">Previous sessions</p>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            title="Refresh"
            onClick={() => void loadSessions()}
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
          <button
            type="button"
            title="New chat"
            onClick={() => {
              startNewChat();
              void loadSessions();
            }}
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-white transition hover:bg-slate-700 dark:bg-sky-600 dark:hover:bg-sky-500"
          >
            <MessageSquarePlus size={16} />
          </button>
        </div>
      </div>

      {/* Compact dataset line */}
      <div className="border-b border-slate-100 px-4 py-2.5 dark:border-slate-800">
        <p className="truncate text-xs text-slate-500">
          <span className="font-medium text-slate-600 dark:text-slate-300">Dataset · </span>
          {datasetName || "Auto-discover"}
        </p>
      </div>

      {/* Previous sessions list */}
      <div className="min-h-0 flex-1 overflow-y-auto p-2 scrollbar-thin">
        {previousSessions.length === 0 ? (
          <div className="m-2 rounded-2xl border border-dashed border-slate-200 px-4 py-10 text-center dark:border-slate-700">
            <p className="text-sm font-medium text-slate-600 dark:text-slate-300">No previous sessions</p>
            <p className="mt-1 text-xs text-slate-400">
              Start a new chat, then older ones will show here.
            </p>
          </div>
        ) : (
          <ul className="space-y-1">
            {previousSessions.map((row) => {
              const isOpening = openingId === row.id;
              return (
                <li key={row.id}>
                  <button
                    type="button"
                    disabled={isOpening}
                    onClick={() => void openSessionInAnalyze(row.id, row.focusMessageId)}
                    className={`group flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left transition
                      hover:bg-sky-50 active:scale-[0.98] active:bg-sky-100
                      focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400
                      disabled:opacity-60
                      dark:hover:bg-slate-800 dark:active:bg-slate-700
                    `}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2 text-sm font-medium leading-snug text-slate-800 group-hover:text-sky-900 dark:text-slate-100 dark:group-hover:text-sky-100">
                        {row.title}
                      </p>
                      <p className="mt-1 truncate text-[11px] text-slate-400 group-hover:text-sky-600/80 dark:group-hover:text-sky-300/80">
                        {isOpening
                          ? "Opening…"
                          : row.timestamp
                            ? `${formatRelative(row.timestamp)} · ${row.subtitle}`
                            : row.subtitle}
                      </p>
                    </div>
                    <ChevronRight
                      size={18}
                      className="shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-sky-500 dark:text-slate-600"
                    />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}

function formatRelative(ts: number): string {
  if (!ts) return "";
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(ts).toLocaleDateString();
}
