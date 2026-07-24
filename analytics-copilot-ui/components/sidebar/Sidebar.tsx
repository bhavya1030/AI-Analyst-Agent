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

  const previousSessions = useMemo(() => {
    const rows = new Map<string, SessionRow>();

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

    for (const id of remoteSessions) {
      if (!id || id === sessionId || rows.has(id)) continue;
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
    <aside className="surface flex h-full w-full flex-col overflow-hidden">
      <div className="panel-header flex items-center justify-between gap-2">
        <div>
          <p className="label-caps">History</p>
          <h2 className="text-sm font-semibold text-slate-900">Sessions</h2>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            title="Refresh"
            onClick={() => void loadSessions()}
            className="btn-ghost h-8 w-8 !p-0"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          </button>
          <button
            type="button"
            title="New chat"
            onClick={() => {
              startNewChat();
              void loadSessions();
            }}
            className="btn-primary h-8 w-8 !rounded-lg !p-0"
          >
            <MessageSquarePlus size={15} />
          </button>
        </div>
      </div>

      <div className="border-b border-slate-100 px-4 py-2.5">
        <p className="truncate text-[11px] text-slate-500">
          <span className="font-medium text-slate-600">Active data · </span>
          {datasetName || "Open-data mode"}
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2 scrollbar-thin">
        {previousSessions.length === 0 ? (
          <div className="m-1 rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 px-3 py-8 text-center">
            <p className="text-sm font-medium text-slate-600">No previous sessions</p>
            <p className="mt-1 text-[11px] leading-5 text-slate-400">
              Start a chat — earlier conversations will appear here.
            </p>
          </div>
        ) : (
          <ul className="space-y-0.5">
            {previousSessions.map((row) => {
              const isOpening = openingId === row.id;
              return (
                <li key={row.id}>
                  <button
                    type="button"
                    disabled={isOpening}
                    onClick={() => void openSessionInAnalyze(row.id, row.focusMessageId)}
                    className="group flex w-full items-center gap-2 rounded-xl px-2.5 py-2.5 text-left transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 disabled:opacity-60"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2 text-[13px] font-medium leading-snug text-slate-800">
                        {row.title}
                      </p>
                      <p className="mt-0.5 truncate text-[11px] text-slate-400">
                        {isOpening
                          ? "Opening…"
                          : row.timestamp
                            ? `${formatRelative(row.timestamp)} · ${row.subtitle}`
                            : row.subtitle}
                      </p>
                    </div>
                    <ChevronRight
                      size={16}
                      className="shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-blue-500"
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
