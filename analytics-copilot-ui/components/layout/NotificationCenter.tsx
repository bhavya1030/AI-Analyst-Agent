"use client";

import { CheckCheck } from "lucide-react";
import { useUiStore } from "@/store/uiStore";
import { formatRelative } from "@/utils/format";

export default function NotificationCenter() {
  const notifications = useUiStore((s) => s.notifications);
  const markNotificationRead = useUiStore((s) => s.markNotificationRead);
  const markAllNotificationsRead = useUiStore((s) => s.markAllNotificationsRead);

  return (
    <div className="dropdown-panel right-0 top-full mt-1.5 w-80 sm:w-96">
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <div>
          <p className="text-xs font-semibold text-foreground">Notifications</p>
          <p className="text-[11px] text-muted-foreground">Platform activity</p>
        </div>
        <button
          type="button"
          className="btn-ghost !px-2 !py-1 !text-[11px]"
          onClick={() => markAllNotificationsRead()}
        >
          <CheckCheck size={13} />
          Mark all read
        </button>
      </div>
      <div className="max-h-80 overflow-y-auto scrollbar-thin">
        {notifications.length === 0 ? (
          <p className="px-3 py-8 text-center text-xs text-muted-foreground">
            No notifications
          </p>
        ) : (
          notifications.map((n) => (
            <button
              key={n.id}
              type="button"
              onClick={() => markNotificationRead(n.id)}
              className={`flex w-full flex-col gap-0.5 border-b border-border/70 px-3 py-2.5 text-left transition hover:bg-surface-muted ${
                n.read ? "opacity-70" : ""
              }`}
            >
              <div className="flex items-center gap-2">
                {!n.read ? (
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                ) : (
                  <span className="h-1.5 w-1.5 shrink-0" />
                )}
                <p className="text-xs font-semibold text-foreground">{n.title}</p>
              </div>
              <p className="pl-3.5 text-[11px] leading-4 text-muted-foreground">{n.body}</p>
              <p className="pl-3.5 text-[10px] text-muted-foreground/80">
                {formatRelative(n.createdAt)}
              </p>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
