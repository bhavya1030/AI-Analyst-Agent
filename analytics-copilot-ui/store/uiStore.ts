import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeMode = "light" | "dark" | "system";
export type AnalysisTab =
  | "overview"
  | "charts"
  | "eda"
  | "forecast"
  | "insights"
  | "tables"
  | "reports";
export type WorkspaceId = "analytics" | "forecasting" | "research";

export interface AppNotification {
  id: string;
  title: string;
  body: string;
  read: boolean;
  createdAt: number;
  kind?: "info" | "success" | "warning";
}

interface UiStore {
  theme: ThemeMode;
  resolvedTheme: "light" | "dark";
  workspaceId: WorkspaceId;
  analysisTab: AnalysisTab;
  settingsOpen: boolean;
  searchOpen: boolean;
  notificationsOpen: boolean;
  mobileChatOpen: boolean;
  notifications: AppNotification[];
  setTheme: (theme: ThemeMode) => void;
  setResolvedTheme: (theme: "light" | "dark") => void;
  setWorkspaceId: (id: WorkspaceId) => void;
  setAnalysisTab: (tab: AnalysisTab) => void;
  setSettingsOpen: (open: boolean) => void;
  setSearchOpen: (open: boolean) => void;
  setNotificationsOpen: (open: boolean) => void;
  setMobileChatOpen: (open: boolean) => void;
  markNotificationRead: (id: string) => void;
  markAllNotificationsRead: () => void;
  pushNotification: (n: Omit<AppNotification, "id" | "createdAt" | "read">) => void;
}

const DEFAULT_NOTIFICATIONS: AppNotification[] = [
  {
    id: "n1",
    title: "Welcome to Analytics Platform",
    body: "Your analysis workspace is ready. Ask a question or upload a dataset.",
    read: false,
    createdAt: Date.now() - 60_000,
    kind: "info",
  },
  {
    id: "n2",
    title: "Sessions sync enabled",
    body: "Chat history, charts, and datasets restore from the server automatically.",
    read: false,
    createdAt: Date.now() - 120_000,
    kind: "success",
  },
];

export const useUiStore = create<UiStore>()(
  persist(
    (set, get) => ({
      theme: "system",
      resolvedTheme: "light",
      workspaceId: "analytics",
      analysisTab: "overview",
      settingsOpen: false,
      searchOpen: false,
      notificationsOpen: false,
      mobileChatOpen: false,
      notifications: DEFAULT_NOTIFICATIONS,

      setTheme: (theme) => set({ theme }),
      setResolvedTheme: (resolvedTheme) => set({ resolvedTheme }),
      setWorkspaceId: (workspaceId) => set({ workspaceId }),
      setAnalysisTab: (analysisTab) => set({ analysisTab }),
      setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
      setSearchOpen: (searchOpen) => set({ searchOpen }),
      setNotificationsOpen: (notificationsOpen) => set({ notificationsOpen }),
      setMobileChatOpen: (mobileChatOpen) => set({ mobileChatOpen }),

      markNotificationRead: (id) =>
        set({
          notifications: get().notifications.map((n) =>
            n.id === id ? { ...n, read: true } : n
          ),
        }),

      markAllNotificationsRead: () =>
        set({
          notifications: get().notifications.map((n) => ({ ...n, read: true })),
        }),

      pushNotification: (n) =>
        set({
          notifications: [
            {
              ...n,
              id: `n-${Date.now()}`,
              createdAt: Date.now(),
              read: false,
            },
            ...get().notifications,
          ].slice(0, 30),
        }),
    }),
    {
      name: "analytics-platform-ui",
      partialize: (s) => ({
        theme: s.theme,
        workspaceId: s.workspaceId,
        analysisTab: s.analysisTab,
      }),
    }
  )
);

export const WORKSPACES: {
  id: WorkspaceId;
  label: string;
  description: string;
}[] = [
  {
    id: "analytics",
    label: "Analytics",
    description: "EDA, charts, and exploratory analysis",
  },
  {
    id: "forecasting",
    label: "Forecasting",
    description: "Time-series prediction and scenarios",
  },
  {
    id: "research",
    label: "Research",
    description: "Open-data discovery and multi-source studies",
  },
];
