"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  Archive,
  ChevronRight,
  Copy,
  MessageSquarePlus,
  MoreHorizontal,
  RefreshCw,
  Search,
  Star,
  Trash2,
  Pencil,
  RotateCcw,
} from "lucide-react";
import { fetchRecentSessions, searchSessions } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { SessionSearchHit, SessionSummary } from "@/types";
import { parseServerTime } from "@/utils/sessionRestore";

type FilterMode = "all" | "recent" | "favorites";

type SessionRow = {
  id: string;
  title: string;
  subtitle: string;
  timestamp: number;
  favorite?: boolean;
  archived?: boolean;
  pinned?: boolean;
  messageCount?: number;
  snippet?: string;
};

function summaryToRow(s: SessionSummary): SessionRow {
  const ts = parseServerTime(s.updated_at || s.last_activity_at);
  const title =
    (s.title && s.title !== "New analysis" ? s.title : "") ||
    s.last_query?.slice(0, 72) ||
    s.dataset_topic ||
    s.dataset_name ||
    s.session_id;
  const subtitle =
    s.dataset_name ||
    s.dataset_topic ||
    (s.archived ? "Archived" : s.message_count ? `${s.message_count} messages` : "Server session");
  return {
    id: s.session_id,
    title,
    subtitle,
    timestamp: ts,
    favorite: Boolean(s.favorite),
    archived: Boolean(s.archived),
    pinned: Boolean(s.pinned),
    messageCount: s.message_count,
  };
}

function hitToRow(h: SessionSearchHit): SessionRow {
  return {
    id: h.session_id,
    title: h.title || h.snippet?.slice(0, 72) || h.session_id,
    subtitle: h.snippet || h.dataset_name || h.dataset_topic || "Search match",
    timestamp: parseServerTime(h.updated_at || h.last_activity_at),
    favorite: Boolean(h.favorite),
    archived: Boolean(h.archived),
    pinned: Boolean(h.pinned),
    messageCount: h.message_count,
    snippet: h.snippet,
  };
}

export default function Sidebar() {
  const {
    sessionId,
    datasetName,
    remoteSessionList,
    sessionsLoading,
    openSessionFromBackend,
    startNewChat,
    refreshRemoteSessions,
    rehydrateActiveSession,
    renameRemoteSession,
    deleteRemoteSession,
    archiveRemoteSession,
    restoreRemoteSession,
    favoriteRemoteSession,
    duplicateRemoteSession,
  } = useChatStore();

  const [filter, setFilter] = useState<FilterMode>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState<SessionSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [recentIds, setRecentIds] = useState<string[] | null>(null);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const loadSessions = useCallback(async () => {
    await refreshRemoteSessions({ includeArchived: true });
  }, [refreshRemoteSessions]);

  useEffect(() => {
    void loadSessions();
    void rehydrateActiveSession();
  }, [loadSessions, rehydrateActiveSession]);

  // Close action menu on outside click
  useEffect(() => {
    if (!menuOpenId) return;
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpenId]);

  // Debounced server search
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    const q = searchQuery.trim();
    if (!q) {
      setSearchHits(null);
      setSearching(false);
      return;
    }
    setSearching(true);
    searchTimer.current = setTimeout(() => {
      void (async () => {
        try {
          const res = await searchSessions(q, { limit: 40 });
          setSearchHits(res.items || []);
        } finally {
          setSearching(false);
        }
      })();
    }, 280);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [searchQuery]);

  // Load recent when filter switches
  useEffect(() => {
    if (filter !== "recent") {
      setRecentIds(null);
      return;
    }
    void (async () => {
      const items = await fetchRecentSessions(25);
      setRecentIds(items.map((s) => s.session_id));
    })();
  }, [filter, remoteSessionList]);

  const rows = useMemo(() => {
    // Search mode overrides list
    if (searchHits) {
      return searchHits
        .filter((h) => h.session_id !== sessionId)
        .map(hitToRow)
        .sort((a, b) => b.timestamp - a.timestamp);
    }

    let list = remoteSessionList.filter((s) => s.session_id !== sessionId);

    if (filter === "favorites") {
      list = list.filter((s) => s.favorite);
    } else if (filter === "recent" && recentIds) {
      const order = new Map(recentIds.map((id, i) => [id, i]));
      list = list
        .filter((s) => order.has(s.session_id) && !s.archived)
        .sort(
          (a, b) =>
            (order.get(a.session_id) ?? 999) - (order.get(b.session_id) ?? 999)
        );
      return list.map(summaryToRow);
    }

    // Pinned / favorites first, then by updated time
    return list
      .map(summaryToRow)
      .sort((a, b) => {
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
        if (a.favorite !== b.favorite) return a.favorite ? -1 : 1;
        return b.timestamp - a.timestamp;
      });
  }, [remoteSessionList, sessionId, filter, recentIds, searchHits]);

  const openSessionInAnalyze = async (targetSessionId: string) => {
    if (!targetSessionId || targetSessionId === sessionId) return;
    setOpeningId(targetSessionId);
    setMenuOpenId(null);
    try {
      await openSessionFromBackend(targetSessionId);
    } finally {
      setOpeningId(null);
      document.getElementById("analyze-panel")?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  };

  const runAction = async (
    id: string,
    action: () => Promise<unknown>
  ) => {
    setBusyId(id);
    setMenuOpenId(null);
    try {
      await action();
    } finally {
      setBusyId(null);
    }
  };

  const handleRename = (id: string, currentTitle: string) => {
    const next = window.prompt("Rename session", currentTitle);
    if (next == null) return;
    const title = next.trim();
    if (!title || title === currentTitle) return;
    void runAction(id, () => renameRemoteSession(id, title));
  };

  const handleDelete = (id: string) => {
    if (!window.confirm("Delete this session? It can be hard-removed from the server.")) return;
    void runAction(id, () => deleteRemoteSession(id, false));
  };

  const isLoading = sessionsLoading || searching;

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
            <RefreshCw size={15} className={isLoading ? "animate-spin" : ""} />
          </button>
          <button
            type="button"
            title="New chat"
            onClick={() => {
              void startNewChat();
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

      {/* Search — compact, same panel style */}
      <div className="border-b border-slate-100 px-3 py-2">
        <div className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50/80 px-2.5 py-1.5">
          <Search size={13} className="shrink-0 text-slate-400" />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search sessions…"
            className="min-w-0 flex-1 bg-transparent text-[12px] text-slate-800 outline-none placeholder:text-slate-400"
            aria-label="Search sessions"
          />
        </div>
        <div className="mt-1.5 flex gap-1">
          {(
            [
              ["all", "All"],
              ["recent", "Recent"],
              ["favorites", "★"],
            ] as const
          ).map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              onClick={() => setFilter(mode)}
              className={`rounded-lg px-2 py-0.5 text-[10px] font-medium transition ${
                filter === mode && !searchHits
                  ? "bg-blue-50 text-blue-700"
                  : "text-slate-400 hover:bg-slate-50 hover:text-slate-600"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2 scrollbar-thin">
        {rows.length === 0 ? (
          <div className="m-1 rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 px-3 py-8 text-center">
            <p className="text-sm font-medium text-slate-600">
              {searchHits
                ? "No matches"
                : filter === "favorites"
                  ? "No favorites yet"
                  : "No previous sessions"}
            </p>
            <p className="mt-1 text-[11px] leading-5 text-slate-400">
              {searchHits
                ? "Try a different search term."
                : "Start a chat — earlier conversations will appear here."}
            </p>
          </div>
        ) : (
          <ul className="space-y-0.5">
            {rows.map((row) => {
              const isOpening = openingId === row.id;
              const isBusy = busyId === row.id;
              const menuOpen = menuOpenId === row.id;
              return (
                <li key={row.id} className="relative">
                  <div
                    className={`group flex w-full items-center gap-1 rounded-xl px-1.5 py-1.5 transition hover:bg-slate-50 ${
                      isOpening || isBusy ? "opacity-60" : ""
                    }`}
                  >
                    <button
                      type="button"
                      disabled={isOpening || isBusy}
                      onClick={() => void openSessionInAnalyze(row.id)}
                      className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1 py-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
                    >
                      {row.favorite ? (
                        <Star
                          size={12}
                          className="mt-0.5 shrink-0 fill-amber-400 text-amber-400"
                        />
                      ) : null}
                      <div className="min-w-0 flex-1">
                        <p className="line-clamp-2 text-[13px] font-medium leading-snug text-slate-800">
                          {row.title}
                          {row.archived ? (
                            <span className="ml-1 text-[10px] font-normal text-slate-400">
                              · archived
                            </span>
                          ) : null}
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

                    {/* Compact actions — no layout redesign */}
                    <div className="relative flex shrink-0 items-center gap-0.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                      <button
                        type="button"
                        title={row.favorite ? "Unfavorite" : "Favorite"}
                        className="btn-ghost h-7 w-7 !p-0"
                        onClick={(e) => {
                          e.stopPropagation();
                          void runAction(row.id, () =>
                            favoriteRemoteSession(row.id, !row.favorite)
                          );
                        }}
                      >
                        <Star
                          size={13}
                          className={
                            row.favorite
                              ? "fill-amber-400 text-amber-400"
                              : "text-slate-400"
                          }
                        />
                      </button>
                      <button
                        type="button"
                        title="More"
                        className="btn-ghost h-7 w-7 !p-0"
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuOpenId(menuOpen ? null : row.id);
                        }}
                      >
                        <MoreHorizontal size={14} className="text-slate-400" />
                      </button>
                    </div>
                  </div>

                  {menuOpen ? (
                    <div
                      ref={menuRef}
                      className="absolute right-2 top-full z-20 mt-0.5 w-40 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-md"
                    >
                      <MenuItem
                        icon={<Pencil size={13} />}
                        label="Rename"
                        onClick={() => handleRename(row.id, row.title)}
                      />
                      <MenuItem
                        icon={<Copy size={13} />}
                        label="Duplicate"
                        onClick={() =>
                          void runAction(row.id, async () => {
                            const dup = await duplicateRemoteSession(row.id);
                            if (dup?.session_id) {
                              await openSessionFromBackend(dup.session_id);
                            }
                          })
                        }
                      />
                      {row.archived ? (
                        <MenuItem
                          icon={<RotateCcw size={13} />}
                          label="Restore"
                          onClick={() =>
                            void runAction(row.id, () => restoreRemoteSession(row.id))
                          }
                        />
                      ) : (
                        <MenuItem
                          icon={<Archive size={13} />}
                          label="Archive"
                          onClick={() =>
                            void runAction(row.id, () => archiveRemoteSession(row.id))
                          }
                        />
                      )}
                      <MenuItem
                        icon={<Trash2 size={13} />}
                        label="Delete"
                        danger
                        onClick={() => handleDelete(row.id)}
                      />
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  danger,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] transition hover:bg-slate-50 ${
        danger ? "text-red-600" : "text-slate-700"
      }`}
    >
      {icon}
      {label}
    </button>
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
