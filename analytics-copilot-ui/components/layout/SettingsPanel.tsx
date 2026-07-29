"use client";

import { Monitor, Moon, Sun, X } from "lucide-react";
import { useUiStore, type ThemeMode } from "@/store/uiStore";

interface SettingsPanelProps {
  onClose: () => void;
}

const THEMES: { id: ThemeMode; label: string; icon: typeof Sun }[] = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
  { id: "system", label: "System", icon: Monitor },
];

export default function SettingsPanel({ onClose }: SettingsPanelProps) {
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);

  return (
    <div className="fixed inset-0 z-[60] flex justify-end bg-black/40 backdrop-blur-sm animate-fade-in">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Close settings"
        onClick={onClose}
      />
      <aside className="relative z-10 flex h-full w-full max-w-md flex-col border-l border-border bg-surface shadow-lift animate-slide-up">
        <div className="flex items-center justify-between border-b border-border px-4 py-3.5">
          <div>
            <p className="label-caps">Preferences</p>
            <h2 className="text-sm font-semibold text-foreground">Settings</h2>
          </div>
          <button type="button" className="btn-icon" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto p-4 scrollbar-thin">
          <section>
            <h3 className="text-xs font-semibold text-foreground">Appearance</h3>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Choose light, dark, or follow system preference.
            </p>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {THEMES.map((t) => {
                const Icon = t.icon;
                const active = theme === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTheme(t.id)}
                    className={`flex flex-col items-center gap-1.5 rounded-xl border px-2 py-3 text-xs font-semibold transition ${
                      active
                        ? "border-accent bg-accent-soft text-accent"
                        : "border-border text-muted-foreground hover:bg-surface-muted"
                    }`}
                  >
                    <Icon size={16} />
                    {t.label}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="surface-muted p-3.5">
            <h3 className="text-xs font-semibold text-foreground">Platform</h3>
            <ul className="mt-2 space-y-1.5 text-[11px] text-muted-foreground">
              <li>· Sessions persist on the analytics backend</li>
              <li>· Dataset paths bind to the active session</li>
              <li>· Optional X-User-Id for multi-user isolation</li>
              <li>· Export / import available from History</li>
            </ul>
          </section>

          <section>
            <h3 className="text-xs font-semibold text-foreground">API</h3>
            <p className="mt-1 break-all rounded-xl border border-border bg-surface-muted px-3 py-2 font-mono text-[11px] text-muted-foreground">
              {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}
            </p>
          </section>
        </div>
      </aside>
    </div>
  );
}
