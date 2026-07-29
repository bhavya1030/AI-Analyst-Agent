"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Bell,
  History,
  Menu,
  MessageSquarePlus,
  Moon,
  Search,
  Settings,
  Sparkles,
  Sun,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import WorkspaceSwitcher from "@/components/layout/WorkspaceSwitcher";
import UserMenu from "@/components/layout/UserMenu";
import NotificationCenter from "@/components/layout/NotificationCenter";
import CommandSearch from "@/components/layout/CommandSearch";
import SettingsPanel from "@/components/layout/SettingsPanel";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { shortId } from "@/utils/format";

export default function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const sessionId = useChatStore((s) => s.sessionId);
  const datasetName = useChatStore((s) => s.datasetName);
  const startNewChat = useChatStore((s) => s.startNewChat);
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);
  const resolvedTheme = useUiStore((s) => s.resolvedTheme);
  const searchOpen = useUiStore((s) => s.searchOpen);
  const setSearchOpen = useUiStore((s) => s.setSearchOpen);
  const settingsOpen = useUiStore((s) => s.settingsOpen);
  const setSettingsOpen = useUiStore((s) => s.setSettingsOpen);
  const notificationsOpen = useUiStore((s) => s.notificationsOpen);
  const setNotificationsOpen = useUiStore((s) => s.setNotificationsOpen);
  const notifications = useUiStore((s) => s.notifications);
  const setMobileChatOpen = useUiStore((s) => s.setMobileChatOpen);
  const unread = notifications.filter((n) => !n.read).length;
  const [mobileNav, setMobileNav] = useState(false);
  const notifRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
        setNotificationsOpen(false);
        setSettingsOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setSearchOpen, setNotificationsOpen, setSettingsOpen]);

  useEffect(() => {
    if (!notificationsOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotificationsOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [notificationsOpen, setNotificationsOpen]);

  const cycleTheme = () => {
    if (theme === "light") setTheme("dark");
    else if (theme === "dark") setTheme("system");
    else setTheme("light");
  };

  const isHistory = pathname?.startsWith("/history");

  return (
    <>
      <header className="nav-shell">
        <div className="mx-auto flex h-14 max-w-[1800px] items-center gap-2 px-3 md:gap-3 md:px-5">
          {/* Brand */}
          <Link
            href="/"
            className="group flex min-w-0 shrink-0 items-center gap-2.5 rounded-xl pr-1 transition"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-soft transition group-hover:shadow-glow">
              <Sparkles size={16} strokeWidth={2.2} />
            </div>
            <div className="hidden min-w-0 sm:block">
              <p className="text-sm font-semibold tracking-tight text-foreground">
                Analytics Platform
              </p>
              <p className="truncate text-[10px] text-muted-foreground">
                AI · Open data · Enterprise
              </p>
            </div>
          </Link>

          <div className="hidden h-6 w-px bg-border md:block" />

          <div className="hidden md:block">
            <WorkspaceSwitcher />
          </div>

          {/* Center search trigger */}
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            className="ml-auto flex min-w-0 max-w-md flex-1 items-center gap-2 rounded-xl border border-border bg-surface-muted/70 px-3 py-2 text-left text-xs text-muted-foreground transition hover:border-accent/40 hover:bg-surface-muted md:ml-2"
          >
            <Search size={14} className="shrink-0" />
            <span className="min-w-0 flex-1 truncate">Search sessions, questions…</span>
            <kbd className="hidden rounded-md border border-border bg-surface px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground sm:inline">
              ⌘K
            </kbd>
          </button>

          {/* Actions */}
          <div className="flex shrink-0 items-center gap-0.5 md:gap-1">
            <button
              type="button"
              title="New analysis"
              className="btn-primary !h-9 !rounded-xl !px-2.5 !text-xs md:!px-3"
              onClick={() => {
                void startNewChat();
                if (pathname !== "/") router.push("/");
              }}
            >
              <MessageSquarePlus size={14} />
              <span className="hidden sm:inline">New</span>
            </button>

            <Link
              href="/history"
              title="Session history"
              className={`btn-icon ${isHistory ? "bg-accent-soft text-accent" : ""}`}
            >
              <History size={17} />
            </Link>

            <button
              type="button"
              title={`Theme: ${theme}`}
              className="btn-icon hidden sm:inline-flex"
              onClick={cycleTheme}
            >
              {resolvedTheme === "dark" ? <Moon size={16} /> : <Sun size={16} />}
            </button>

            <div className="relative" ref={notifRef}>
              <button
                type="button"
                title="Notifications"
                className="btn-icon relative"
                onClick={() => setNotificationsOpen(!notificationsOpen)}
              >
                <Bell size={16} />
                {unread > 0 ? (
                  <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-accent ring-2 ring-surface" />
                ) : null}
              </button>
              {notificationsOpen ? <NotificationCenter /> : null}
            </div>

            <button
              type="button"
              title="Settings"
              className="btn-icon"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings size={16} />
            </button>

            <div className="hidden sm:block">
              <UserMenu />
            </div>

            <button
              type="button"
              className="btn-icon lg:hidden"
              onClick={() => setMobileNav((v) => !v)}
              aria-label="Menu"
            >
              {mobileNav ? <X size={17} /> : <Menu size={17} />}
            </button>
          </div>
        </div>

        {/* Context strip */}
        <div className="border-t border-border/70 bg-surface-muted/40">
          <div className="mx-auto flex max-w-[1800px] items-center gap-2 overflow-x-auto px-3 py-1.5 text-[11px] text-muted-foreground scrollbar-thin md:px-5">
            <span className="chip !py-0.5">Session · {shortId(sessionId)}</span>
            <span
              className={
                datasetName ? "chip chip-success !py-0.5" : "chip chip-accent !py-0.5"
              }
            >
              {datasetName
                ? datasetName.length > 36
                  ? `${datasetName.slice(0, 36)}…`
                  : datasetName
                : "Open-data mode"}
            </span>
            <span className="hidden text-muted-foreground/80 md:inline">
              Analysis canvas · AI copilot
            </span>
            <button
              type="button"
              className="ml-auto inline-flex items-center gap-1 rounded-lg px-2 py-0.5 font-medium text-accent hover:bg-accent-soft lg:hidden"
              onClick={() => setMobileChatOpen(true)}
            >
              Open chat
            </button>
          </div>
        </div>

        {mobileNav ? (
          <div className="border-t border-border bg-surface p-3 animate-slide-down md:hidden">
            <WorkspaceSwitcher />
            <div className="mt-3 flex gap-2">
              <button type="button" className="btn-secondary flex-1" onClick={cycleTheme}>
                Theme · {theme}
              </button>
              <UserMenu />
            </div>
          </div>
        ) : null}
      </header>

      {searchOpen ? <CommandSearch onClose={() => setSearchOpen(false)} /> : null}
      {settingsOpen ? <SettingsPanel onClose={() => setSettingsOpen(false)} /> : null}
    </>
  );
}
