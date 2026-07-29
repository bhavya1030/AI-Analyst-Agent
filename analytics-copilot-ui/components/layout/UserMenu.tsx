"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut, User } from "lucide-react";

const USER_ID =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_USER_ID) || "anonymous";

export default function UserMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const label = USER_ID === "anonymous" ? "Analyst" : USER_ID;

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-2 py-1.5 transition hover:bg-surface-muted"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-[11px] font-bold text-white">
          {label.slice(0, 1).toUpperCase()}
        </span>
        <span className="hidden max-w-[100px] truncate text-xs font-semibold text-foreground lg:inline">
          {label}
        </span>
        <ChevronDown size={14} className="text-muted-foreground" />
      </button>

      {open ? (
        <div className="dropdown-panel right-0 top-full mt-1.5 w-56 p-1.5">
          <div className="border-b border-border px-2.5 py-2">
            <p className="text-xs font-semibold text-foreground">{label}</p>
            <p className="text-[11px] text-muted-foreground">Role · Analyst</p>
          </div>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-xs text-foreground hover:bg-surface-muted"
            onClick={() => setOpen(false)}
          >
            <User size={14} className="text-muted-foreground" />
            Profile
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-xs text-muted-foreground hover:bg-surface-muted"
            onClick={() => setOpen(false)}
          >
            <LogOut size={14} />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
