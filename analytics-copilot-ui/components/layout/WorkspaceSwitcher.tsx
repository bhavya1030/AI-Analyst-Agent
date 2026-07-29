"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronsUpDown, Layers } from "lucide-react";
import { useUiStore, WORKSPACES, type WorkspaceId } from "@/store/uiStore";

export default function WorkspaceSwitcher() {
  const workspaceId = useUiStore((s) => s.workspaceId);
  const setWorkspaceId = useUiStore((s) => s.setWorkspaceId);
  const setAnalysisTab = useUiStore((s) => s.setAnalysisTab);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const current = WORKSPACES.find((w) => w.id === workspaceId) || WORKSPACES[0];

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const select = (id: WorkspaceId) => {
    setWorkspaceId(id);
    if (id === "forecasting") setAnalysisTab("forecast");
    else if (id === "research") setAnalysisTab("overview");
    else setAnalysisTab("overview");
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-2.5 py-1.5 text-left transition hover:bg-surface-muted"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <Layers size={14} />
        </span>
        <span className="min-w-0">
          <span className="block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Workspace
          </span>
          <span className="block max-w-[120px] truncate text-xs font-semibold text-foreground">
            {current.label}
          </span>
        </span>
        <ChevronsUpDown size={14} className="text-muted-foreground" />
      </button>

      {open ? (
        <div className="dropdown-panel left-0 top-full mt-1.5 w-72 p-1.5">
          {WORKSPACES.map((w) => {
            const active = w.id === workspaceId;
            return (
              <button
                key={w.id}
                type="button"
                onClick={() => select(w.id)}
                className={`flex w-full items-start gap-2 rounded-xl px-2.5 py-2.5 text-left transition ${
                  active ? "bg-accent-soft" : "hover:bg-surface-muted"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-foreground">{w.label}</p>
                  <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                    {w.description}
                  </p>
                </div>
                {active ? <Check size={14} className="mt-0.5 shrink-0 text-accent" /> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
