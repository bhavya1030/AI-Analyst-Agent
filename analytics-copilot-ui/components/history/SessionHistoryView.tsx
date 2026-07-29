"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  Archive,
  Copy,
  Download,
  Filter,
  MoreHorizontal,
  Pencil,
  RotateCcw,
  Search,
  Star,
  Trash2,
  Upload,
} from "lucide-react";
import {
  exportSession,
  importSession,
  searchSessions,
} from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { SessionSearchHit, SessionSummary } from "@/types";
import { parseServerTime } from "@/utils/sessionRestore";
import { downloadJson, formatRelative } from "@/utils/format";

type FilterMode = "all" | "favorites" | "archived" | "active";

type Row = {
  id: string;
  title: string;
  subtitle: string;
  preview: string;
  timestamp: number;
  favorite?: boolean;
  archived?: boolean;
  messageCount?: number;
  dataset?: string;
};

function summaryToRow(s: SessionSummary): Row {
  const title =
    (s.title && s.title !== "New analysis" ? s.title : "") ||
    s.last_query?.slice(0, 80) ||
    s.dataset_topic ||
    s.dataset_name ||
    s.session_id;
  return {
    id: s.session_id,
    title,
    subtitle: s.dataset_name || s.dataset_topic || "Session",
    preview:
      s.conversation_summary ||
      s.last_query ||
      `${s.message_count ?? 0} messages`,
    timestamp: parseServerTime(s.updated_at || s.last_activity_at),
    favorite: Boolean(s.favorite),
    archived: Boolean(s.archived),
    messageCount: s.message_count,
    dataset: s.dataset_name || s.dataset_topic || undefined,
  };
}

function hitToRow(h: SessionSearchHit): Row {
  return {
    id: h.session_id,
    title: h.title || h.snippet?.slice(0, 80) || h.session_id,
    subtitle: h.dataset_name || h.dataset_topic || "Search match",
    preview: h.snippet || "",
    timestamp: parseServerTime(h.updated_at || h.last_activity_at),
    favorite: Boolean(h.favorite),
    archived: Boolean(h.archived),
    messageCount: h.message_count,
    dataset: h.dataset_name || h.dataset_topic || undefined,
  };
}

export default function SessionHistoryView() {
  const router = useRouter();
  const {
    remoteSessionList,
    sessionsLoading,
    refreshRemoteSessions,
    openSessionFromBackend,
    renameRemoteSession,
    deleteRemoteSession,
    archiveRemoteSession,
    restoreRemoteSession,
    favoriteRemoteSession,
    duplicateRemoteSession,
  } = useChatStore();

  const [filter, setFilter] = useState<FilterMode>("all");
  const [q, setQ] = useState("");
  const [searchHits, setSearchHits] = useState<SessionSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    await refreshRemoteSessions({ includeArchived: true });
  }, [refreshRemoteSessions]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!menuId) return;
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuId(null);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuId]);

  useEffect(() => {
    const query = q.trim();
    if (!query) {
      setSearchHits(null);
      setSearching(false);
      return;
    }
    setSearching(true);
    const t = setTimeout(() => {
      void (async () => {
        try {
          const res = await searchSessions(query, { limit: 50 });
          setSearchHits(res.items || []);
        } finally {
          setSearching(false);
        }
      })();
    }, 280);
    return () => clearTimeout(t);
  }, [q]);

  const rows = useMemo(() => {
    if (searchHits) {
      return searchHits.map(hitToRow).sort((a, b) => b.timestamp - a.timestamp);
    }
    let list = remoteSessionList.map(summaryToRow);
    if (filter === "favorites") list = list.filter((r) => r.favorite);
    else if (filter === "archived") list = list.filter((r) => r.archived);
    else if (filter === "active") list = list.filter((r) => !r.archived);
    return list.sort((a, b) => {
      if (a.favorite !== b.favorite) return a.favorite ? -1 : 1;
      return b.timestamp - a.timestamp;
    });
  }, [remoteSessionList, filter, searchHits]);

  const selected = rows.find((r) => r.id === selectedId) || rows[0] || null;

  const run = async (id: string, fn: () => Promise<unknown>) => {
    setBusyId(id);
    setMenuId(null);
    try {
      await fn();
    } finally {
      setBusyId(null);
    }
  };

  const openSession = async (id: string) => {
    setBusyId(id);
    try {
      await openSessionFromBackend(id);
      router.push("/");
    } finally {
      setBusyId(null);
    }
  };

  const handleRename = (id: string, current: string) => {
    const next = window.prompt("Rename session", current);
    if (next == null) return;
    const title = next.trim();
    if (!title || title === current) return;
    void run(id, () => renameRemoteSession(id, title));
  };

  const handleDelete = (id: string) => {
    if (!window.confirm("Delete this session from the server?")) return;
    void run(id, () => deleteRemoteSession(id, false));
  };

  const handleExport = async (id: string) => {
    await run(id, async () => {
      const bundle = await exportSession(id);
      if (bundle) downloadJson(`session-${id}.json`, bundle);
    });
  };

  const handleImport = async (file: File) => {
    try {
      const text = await file.text();
      const bundle = JSON.parse(text) as Record<string, unknown>;
      const result = await importSession({ bundle });
      await load();
      if (result?.session_id) {
        setSelectedId(result.session_id);
      }
    } catch {
      window.alert("Import failed. Provide a valid session export JSON.");
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-[1600px] flex-col gap-3 p-3 md:p-5 animate-fade-in">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="label-caps text-accent">Library</p>
          <h1 className="text-xl font-semibold tracking-tight text-foreground md:text-2xl">
            Session history
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Search, manage, export, and restore analysis sessions.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleImport(f);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            className="btn-secondary"
            onClick={() => fileRef.current?.click()}
          >
            <Upload size={14} />
            Import
          </button>
          <button type="button" className="btn-secondary" onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="surface flex flex-wrap items-center gap-2 p-2.5 md:p-3">
        <div className="flex min-w-[200px] flex-1 items-center gap-2 rounded-xl border border-border bg-surface-muted/60 px-3 py-2">
          <Search size={14} className="text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search sessions…"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          {searching ? (
            <span className="text-[10px] text-muted-foreground">…</span>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          <Filter size={13} className="text-muted-foreground" />
          {(
            [
              ["all", "All"],
              ["active", "Active"],
              ["favorites", "Favorites"],
              ["archived", "Archived"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              className={`tab-btn ${
                filter === id && !searchHits ? "tab-btn-active" : "tab-btn-idle"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_340px]">
        {/* List */}
        <div className="surface flex min-h-0 flex-col overflow-hidden">
          <div className="panel-header flex items-center justify-between">
            <p className="text-xs font-semibold text-foreground">
              {rows.length} session{rows.length === 1 ? "" : "s"}
              {sessionsLoading ? " · loading" : ""}
            </p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2 scrollbar-thin">
            {rows.length === 0 ? (
              <div className="empty-state m-2">
                <p className="text-sm font-semibold text-foreground">No sessions</p>
                <p className="mt-1 text-[12px] text-muted-foreground">
                  Start an analysis from the workspace, or import a bundle.
                </p>
              </div>
            ) : (
              <ul className="space-y-1">
                {rows.map((row) => {
                  const active = selected?.id === row.id;
                  const busy = busyId === row.id;
                  return (
                    <li key={row.id} className="relative">
                      <div
                        className={`group flex items-stretch gap-1 rounded-xl border transition ${
                          active
                            ? "border-accent/40 bg-accent-soft/50"
                            : "border-transparent hover:border-border hover:bg-surface-muted"
                        } ${busy ? "opacity-60" : ""}`}
                      >
                        <button
                          type="button"
                          className="min-w-0 flex-1 px-3 py-3 text-left"
                          onClick={() => setSelectedId(row.id)}
                          onDoubleClick={() => void openSession(row.id)}
                        >
                          <div className="flex items-start gap-2">
                            {row.favorite ? (
                              <Star
                                size={13}
                                className="mt-0.5 shrink-0 fill-amber-400 text-amber-400"
                              />
                            ) : null}
                            <div className="min-w-0 flex-1">
                              <p className="line-clamp-1 text-sm font-semibold text-foreground">
                                {row.title}
                                {row.archived ? (
                                  <span className="ml-1 text-[10px] font-normal text-muted-foreground">
                                    · archived
                                  </span>
                                ) : null}
                              </p>
                              <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-muted-foreground">
                                {row.preview}
                              </p>
                              <p className="mt-1 text-[10px] text-muted-foreground">
                                {formatRelative(row.timestamp)}
                                {row.dataset ? ` · ${row.dataset}` : ""}
                                {row.messageCount != null
                                  ? ` · ${row.messageCount} msgs`
                                  : ""}
                              </p>
                            </div>
                          </div>
                        </button>
                        <div className="flex shrink-0 items-center gap-0.5 pr-1.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                          <button
                            type="button"
                            title="Favorite"
                            className="btn-icon !h-8 !w-8"
                            onClick={() =>
                              void run(row.id, () =>
                                favoriteRemoteSession(row.id, !row.favorite)
                              )
                            }
                          >
                            <Star
                              size={13}
                              className={
                                row.favorite
                                  ? "fill-amber-400 text-amber-400"
                                  : ""
                              }
                            />
                          </button>
                          <button
                            type="button"
                            title="More"
                            className="btn-icon !h-8 !w-8"
                            onClick={() =>
                              setMenuId(menuId === row.id ? null : row.id)
                            }
                          >
                            <MoreHorizontal size={14} />
                          </button>
                        </div>
                      </div>

                      {menuId === row.id ? (
                        <div
                          ref={menuRef}
                          className="dropdown-panel right-2 top-full z-20 mt-1 w-44 p-1"
                        >
                          <MenuBtn
                            icon={<Pencil size={13} />}
                            label="Rename"
                            onClick={() => handleRename(row.id, row.title)}
                          />
                          <MenuBtn
                            icon={<Copy size={13} />}
                            label="Duplicate"
                            onClick={() =>
                              void run(row.id, async () => {
                                const dup = await duplicateRemoteSession(row.id);
                                if (dup?.session_id) setSelectedId(dup.session_id);
                              })
                            }
                          />
                          <MenuBtn
                            icon={<Download size={13} />}
                            label="Export"
                            onClick={() => void handleExport(row.id)}
                          />
                          {row.archived ? (
                            <MenuBtn
                              icon={<RotateCcw size={13} />}
                              label="Restore"
                              onClick={() =>
                                void run(row.id, () => restoreRemoteSession(row.id))
                              }
                            />
                          ) : (
                            <MenuBtn
                              icon={<Archive size={13} />}
                              label="Archive"
                              onClick={() =>
                                void run(row.id, () => archiveRemoteSession(row.id))
                              }
                            />
                          )}
                          <MenuBtn
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
        </div>

        {/* Preview */}
        <div className="surface flex min-h-0 flex-col overflow-hidden">
          <div className="panel-header">
            <p className="label-caps">Preview</p>
            <h2 className="text-sm font-semibold text-foreground">Session detail</h2>
          </div>
          {selected ? (
            <div className="flex min-h-0 flex-1 flex-col p-4 animate-slide-up">
              <h3 className="text-base font-semibold text-foreground">{selected.title}</h3>
              <p className="mt-1 text-xs text-muted-foreground">{selected.subtitle}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {selected.favorite ? (
                  <span className="chip chip-warning">Favorite</span>
                ) : null}
                {selected.archived ? (
                  <span className="chip">Archived</span>
                ) : (
                  <span className="chip chip-success">Active</span>
                )}
                {selected.messageCount != null ? (
                  <span className="chip">{selected.messageCount} messages</span>
                ) : null}
              </div>
              <div className="mt-4 flex-1 overflow-y-auto rounded-xl border border-border bg-surface-muted p-3 scrollbar-thin">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Preview
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-foreground/90">
                  {selected.preview || "No preview text for this session."}
                </p>
                <p className="mt-4 text-[11px] text-muted-foreground">
                  Updated {formatRelative(selected.timestamp)}
                </p>
                <p className="mt-1 break-all font-mono text-[10px] text-muted-foreground">
                  {selected.id}
                </p>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-primary flex-1"
                  disabled={busyId === selected.id}
                  onClick={() => void openSession(selected.id)}
                >
                  Open in workspace
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => void handleExport(selected.id)}
                >
                  <Download size={14} />
                  Export
                </button>
              </div>
            </div>
          ) : (
            <div className="empty-state m-4 flex-1">
              <p className="text-sm font-medium text-muted-foreground">
                Select a session to preview
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MenuBtn({
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
      className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[12px] transition hover:bg-surface-muted ${
        danger ? "text-danger" : "text-foreground"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
