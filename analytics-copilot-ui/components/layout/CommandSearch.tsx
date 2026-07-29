"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Clock, Search, Star, X } from "lucide-react";
import { searchSessions } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { SessionSearchHit, SessionSummary } from "@/types";
import { parseServerTime } from "@/utils/sessionRestore";
import { formatRelative } from "@/utils/format";

interface CommandSearchProps {
  onClose: () => void;
}

export default function CommandSearch({ onClose }: CommandSearchProps) {
  const router = useRouter();
  const remoteSessionList = useChatStore((s) => s.remoteSessionList);
  const openSessionFromBackend = useChatStore((s) => s.openSessionFromBackend);
  const refreshRemoteSessions = useChatStore((s) => s.refreshRemoteSessions);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SessionSearchHit[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void refreshRemoteSessions({ includeArchived: true });
  }, [refreshRemoteSessions]);

  useEffect(() => {
    const query = q.trim();
    if (!query) {
      setHits(null);
      return;
    }
    setLoading(true);
    const t = setTimeout(() => {
      void (async () => {
        try {
          const res = await searchSessions(query, { limit: 20 });
          setHits(res.items || []);
        } finally {
          setLoading(false);
        }
      })();
    }, 220);
    return () => clearTimeout(t);
  }, [q]);

  const recent = useMemo(() => {
    return [...remoteSessionList]
      .filter((s) => !s.archived)
      .sort(
        (a, b) =>
          parseServerTime(b.updated_at || b.last_activity_at) -
          parseServerTime(a.updated_at || a.last_activity_at)
      )
      .slice(0, 8);
  }, [remoteSessionList]);

  const open = async (id: string) => {
    onClose();
    router.push("/");
    await openSessionFromBackend(id);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 p-4 pt-[12vh] backdrop-blur-sm animate-fade-in">
      <div
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-border bg-surface-elevated shadow-lift animate-slide-up"
        role="dialog"
        aria-modal="true"
        aria-label="Search sessions"
      >
        <div className="flex items-center gap-2 border-b border-border px-3 py-3">
          <Search size={16} className="text-muted-foreground" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search sessions, titles, messages…"
            className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
          {loading ? (
            <span className="text-[11px] text-muted-foreground">Searching…</span>
          ) : null}
          <button type="button" className="btn-icon !h-8 !w-8" onClick={onClose}>
            <X size={15} />
          </button>
        </div>

        <div className="max-h-[50vh] overflow-y-auto p-2 scrollbar-thin">
          {hits ? (
            hits.length === 0 ? (
              <p className="px-3 py-8 text-center text-xs text-muted-foreground">
                No matches for “{q}”
              </p>
            ) : (
              hits.map((h) => (
                <ResultRow
                  key={h.session_id}
                  title={h.title || h.session_id}
                  subtitle={h.snippet || h.dataset_name || "Session"}
                  ts={parseServerTime(h.updated_at || h.last_activity_at)}
                  favorite={h.favorite}
                  onClick={() => void open(h.session_id)}
                />
              ))
            )
          ) : (
            <>
              <p className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Recent
              </p>
              {recent.map((s) => (
                <ResultRow
                  key={s.session_id}
                  title={sessionTitle(s)}
                  subtitle={s.dataset_name || s.dataset_topic || "Session"}
                  ts={parseServerTime(s.updated_at || s.last_activity_at)}
                  favorite={s.favorite}
                  onClick={() => void open(s.session_id)}
                />
              ))}
              {recent.length === 0 ? (
                <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                  No sessions yet
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>
      <button
        type="button"
        className="absolute inset-0 -z-10 cursor-default"
        aria-label="Close search"
        onClick={onClose}
      />
    </div>
  );
}

function sessionTitle(s: SessionSummary): string {
  if (s.title && s.title !== "New analysis") return s.title;
  return s.last_query?.slice(0, 72) || s.dataset_topic || s.session_id;
}

function ResultRow({
  title,
  subtitle,
  ts,
  favorite,
  onClick,
}: {
  title: string;
  subtitle: string;
  ts: number;
  favorite?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-start gap-2 rounded-xl px-2.5 py-2.5 text-left transition hover:bg-surface-muted"
    >
      <Clock size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-semibold text-foreground">{title}</p>
        <p className="truncate text-[11px] text-muted-foreground">{subtitle}</p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {favorite ? <Star size={12} className="fill-amber-400 text-amber-400" /> : null}
        <span className="text-[10px] text-muted-foreground">{formatRelative(ts)}</span>
      </div>
    </button>
  );
}
