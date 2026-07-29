import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  archiveSession as apiArchiveSession,
  createSession as apiCreateSession,
  deleteSession as apiDeleteSession,
  duplicateSession as apiDuplicateSession,
  favoriteSession as apiFavoriteSession,
  fetchSessionDetail,
  fetchSessions,
  renameSession as apiRenameSession,
  restoreSession as apiRestoreSession,
  updateSession as apiUpdateSession,
} from "@/services/api";
import { snapshotFromSessionDetail } from "@/utils/sessionRestore";
import {
  ChatMessage,
  ForecastResult,
  HistoryEntry,
  SessionDetail,
  SessionSnapshot,
  SessionState,
  SessionSummary,
} from "@/types";

interface ChatStore extends SessionState {
  loading: boolean;
  remoteSessionList: SessionSummary[];
  sessionsLoading: boolean;
  addMessage: (message: ChatMessage) => void;
  setForecast: (forecast: ForecastResult | null) => void;
  setDatasetName: (name: string) => void;
  setFilePath: (path: string) => void;
  setSuggestions: (suggestions: string[]) => void;
  setHypotheses: (hypotheses: string[]) => void;
  setSessionId: (sessionId: string) => void;
  setActiveAssistantId: (id: string | null) => void;
  addHistoryEntry: (entry: HistoryEntry) => void;
  resetConversation: (options?: { keepDataset?: boolean }) => void;
  setLoading: (value: boolean) => void;
  clearDataset: () => void;
  /** Snapshot active UI state (ephemeral only) */
  saveCurrentSession: () => void;
  /** Apply backend detail as active session (full restore) */
  hydrateFromSessionDetail: (detail: SessionDetail) => void;
  /** Open session: prefer backend detail, fall back to empty */
  openSession: (
    sessionId: string,
    options?: { focusMessageId?: string; detail?: SessionDetail | null }
  ) => void;
  /** Fetch full detail from backend and restore chat/charts/analysis/dataset */
  openSessionFromBackend: (
    sessionId: string,
    options?: { focusMessageId?: string }
  ) => Promise<boolean>;
  /** Rehydrate the active sessionId from the backend (page reload) */
  rehydrateActiveSession: () => Promise<void>;
  /** Load session list from backend */
  refreshRemoteSessions: (options?: {
    q?: string;
    includeArchived?: boolean;
  }) => Promise<SessionSummary[]>;
  /** Create server session + clear chat */
  startNewChat: () => Promise<void>;
  /** Ensure current session exists on server */
  ensureServerSession: (title?: string) => Promise<string>;
  /** Lifecycle actions (backend) */
  renameRemoteSession: (sessionId: string, title: string) => Promise<boolean>;
  deleteRemoteSession: (sessionId: string, hard?: boolean) => Promise<boolean>;
  archiveRemoteSession: (sessionId: string) => Promise<boolean>;
  restoreRemoteSession: (sessionId: string) => Promise<boolean>;
  favoriteRemoteSession: (sessionId: string, favorite?: boolean) => Promise<boolean>;
  duplicateRemoteSession: (sessionId: string, title?: string) => Promise<SessionSummary | null>;
}

function emptySnapshot(sessionId: string): SessionSnapshot {
  return {
    sessionId,
    datasetName: "",
    filePath: "",
    messages: [],
    charts: [],
    forecast: null,
    suggestions: [],
    hypotheses: [],
    activeAssistantId: null,
    updatedAt: Date.now(),
  };
}

function snapshotFromState(state: SessionState): SessionSnapshot {
  return {
    sessionId: state.sessionId,
    datasetName: state.datasetName,
    filePath: state.filePath,
    messages: state.messages,
    charts: state.charts,
    forecast: state.forecast,
    suggestions: state.suggestions,
    hypotheses: state.hypotheses,
    activeAssistantId: state.activeAssistantId,
    updatedAt: Date.now(),
  };
}

function applySnapshot(snapshot: SessionSnapshot) {
  const lastAssistant =
    [...snapshot.messages].reverse().find((m) => m.role === "assistant") || null;
  return {
    sessionId: snapshot.sessionId,
    datasetName: snapshot.datasetName,
    filePath: snapshot.filePath,
    messages: snapshot.messages,
    charts: snapshot.charts?.length
      ? snapshot.charts
      : lastAssistant?.charts || [],
    forecast: snapshot.forecast || lastAssistant?.forecast || null,
    suggestions: snapshot.suggestions?.length
      ? snapshot.suggestions
      : lastAssistant?.suggestions || [],
    hypotheses: snapshot.hypotheses?.length
      ? snapshot.hypotheses
      : lastAssistant?.hypotheses || [],
    activeAssistantId: snapshot.activeAssistantId || lastAssistant?.id || null,
  };
}

function patchRemoteList(
  list: SessionSummary[],
  sessionId: string,
  patch: Partial<SessionSummary> | null
): SessionSummary[] {
  if (patch === null) {
    return list.filter((s) => s.session_id !== sessionId);
  }
  const idx = list.findIndex((s) => s.session_id === sessionId);
  if (idx < 0) return list;
  const next = [...list];
  next[idx] = { ...next[idx], ...patch };
  return next;
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessionId: `session-${Date.now()}`,
      datasetName: "",
      filePath: "",
      messages: [],
      charts: [],
      forecast: null,
      suggestions: [],
      hypotheses: [],
      history: [],
      activeAssistantId: null,
      sessionsById: {},
      remoteSessionList: [],
      loading: false,
      sessionsLoading: false,

      addMessage: (message) => {
        const state = get();
        const next = [...state.messages, message];
        const patch: Partial<ChatStore> = { messages: next };

        if (message.role === "assistant") {
          patch.activeAssistantId = message.id;
          patch.charts = message.charts || [];
          patch.forecast = message.forecast || null;
          patch.suggestions = message.suggestions || [];
          patch.hypotheses = message.hypotheses || [];
        }

        if (message.role === "user") {
          const entry: HistoryEntry = {
            id: `${state.sessionId}:${message.id}`,
            title: message.text.slice(0, 60) || "Question",
            sessionId: state.sessionId,
            preview: message.text,
            timestamp: message.timestamp || Date.now(),
            datasetName: state.datasetName || undefined,
            messageId: message.id,
          };
          patch.history = [entry, ...state.history.filter((h) => h.id !== entry.id)].slice(
            0,
            50
          );
        }

        // Ephemeral UI cache only — durable history lives on the backend
        const nextState = { ...state, ...patch } as SessionState;
        const snap = snapshotFromState(nextState);
        patch.sessionsById = {
          ...state.sessionsById,
          [state.sessionId]: snap,
        };

        set(patch);
      },

      setForecast: (forecast) => set({ forecast }),
      setDatasetName: (name) => set({ datasetName: name }),
      setFilePath: (path) => set({ filePath: path }),
      setSuggestions: (suggestions) => set({ suggestions }),
      setHypotheses: (hypotheses) => set({ hypotheses }),
      setSessionId: (sessionId) => set({ sessionId }),
      setActiveAssistantId: (id) => set({ activeAssistantId: id }),
      addHistoryEntry: (entry) =>
        set({
          history: [entry, ...get().history.filter((h) => h.id !== entry.id)].slice(0, 50),
        }),

      saveCurrentSession: () => {
        const state = get();
        const snap = snapshotFromState(state);
        set({
          sessionsById: {
            ...state.sessionsById,
            [state.sessionId]: snap,
          },
        });
      },

      hydrateFromSessionDetail: (detail) => {
        const snap = snapshotFromSessionDetail(detail);
        const state = get();
        set({
          sessionsById: { ...state.sessionsById, [snap.sessionId]: snap },
          ...applySnapshot(snap),
        });
      },

      openSession: (sessionId, options) => {
        const state = get();
        if (!sessionId) return;

        const leaving = snapshotFromState(state);
        const sessionsById = {
          ...(state.sessionsById || {}),
          [state.sessionId]: leaving,
        };

        if (sessionId === state.sessionId) {
          if (options?.focusMessageId) {
            const assistant = state.messages.find(
              (m, idx) =>
                m.role === "assistant" &&
                state.messages[idx - 1]?.id === options.focusMessageId
            );
            set({
              sessionsById,
              activeAssistantId: assistant?.id || state.activeAssistantId,
            });
          } else {
            set({ sessionsById });
          }
          return;
        }

        // Prefer full backend detail when provided
        if (options?.detail) {
          const snap = snapshotFromSessionDetail(options.detail);
          set({
            sessionsById: { ...sessionsById, [sessionId]: snap },
            ...applySnapshot(snap),
          });
          if (options?.focusMessageId) {
            const msgs = snap.messages;
            const assistant = msgs.find(
              (m, idx) =>
                m.role === "assistant" && msgs[idx - 1]?.id === options.focusMessageId
            );
            if (assistant) set({ activeAssistantId: assistant.id });
          }
          return;
        }

        // Ephemeral cache only if we already hydrated from backend this session
        const cached = sessionsById[sessionId];
        if (cached && cached.messages?.length) {
          set({
            sessionsById,
            ...applySnapshot(cached),
          });
          return;
        }

        set({
          sessionsById: {
            ...sessionsById,
            [sessionId]: sessionsById[sessionId] || emptySnapshot(sessionId),
          },
          sessionId,
          datasetName: "",
          filePath: "",
          messages: [],
          charts: [],
          forecast: null,
          suggestions: [],
          hypotheses: [],
          activeAssistantId: null,
        });
      },

      openSessionFromBackend: async (sessionId, options) => {
        if (!sessionId) return false;
        const state = get();
        get().saveCurrentSession();

        if (sessionId === state.sessionId && state.messages.length > 0 && !options?.focusMessageId) {
          // Already active with content — still refresh from server for consistency
        }

        const detail = await fetchSessionDetail(sessionId);
        if (detail) {
          get().openSession(sessionId, {
            focusMessageId: options?.focusMessageId,
            detail,
          });
          return true;
        }

        get().openSession(sessionId, { focusMessageId: options?.focusMessageId });
        return false;
      },

      rehydrateActiveSession: async () => {
        const { sessionId } = get();
        if (!sessionId) return;
        const detail = await fetchSessionDetail(sessionId);
        if (detail) {
          get().hydrateFromSessionDetail(detail);
        }
      },

      refreshRemoteSessions: async (options) => {
        set({ sessionsLoading: true });
        try {
          const items = await fetchSessions({
            limit: 100,
            includeArchived: options?.includeArchived ?? true,
            q: options?.q,
          });
          set({ remoteSessionList: items });
          return items;
        } finally {
          set({ sessionsLoading: false });
        }
      },

      ensureServerSession: async (title?: string) => {
        const state = get();
        const created = await apiCreateSession({
          session_id: state.sessionId,
          title: title || "New analysis",
          dataset_name: state.datasetName || undefined,
          dataset_path: state.filePath || undefined,
        });
        const sid = created?.session_id || state.sessionId;
        if (created?.session_id) {
          set({ sessionId: created.session_id });
        }
        // Idempotent create does not re-bind dataset — patch if we have one
        if (state.datasetName || state.filePath) {
          await apiUpdateSession(sid, {
            dataset_name: state.datasetName || undefined,
            dataset_path: state.filePath || undefined,
            dataset_topic: state.datasetName || undefined,
            title:
              title && title !== "New analysis"
                ? title
                : undefined,
          });
        }
        void get().refreshRemoteSessions();
        return sid;
      },

      startNewChat: async () => {
        const state = get();
        const sessionsById = {
          ...state.sessionsById,
          [state.sessionId]: snapshotFromState(state),
        };

        const created = await apiCreateSession({
          title: "New analysis",
          dataset_name: state.datasetName || undefined,
          dataset_path: state.filePath || undefined,
        });
        const newId = created?.session_id || `session-${Date.now()}`;

        set({
          sessionsById: {
            ...sessionsById,
            [newId]: emptySnapshot(newId),
          },
          sessionId: newId,
          messages: [],
          charts: [],
          forecast: null,
          suggestions: [],
          hypotheses: [],
          activeAssistantId: null,
          loading: false,
          datasetName: state.datasetName,
          filePath: state.filePath,
        });

        void get().refreshRemoteSessions();
      },

      renameRemoteSession: async (sessionId, title) => {
        const result = await apiRenameSession(sessionId, title);
        if (!result) return false;
        set({
          remoteSessionList: patchRemoteList(get().remoteSessionList, sessionId, {
            title: result.title || title,
          }),
        });
        return true;
      },

      deleteRemoteSession: async (sessionId, hard = false) => {
        const ok = await apiDeleteSession(sessionId, hard);
        if (!ok) return false;
        set({
          remoteSessionList: patchRemoteList(get().remoteSessionList, sessionId, null),
        });
        const state = get();
        if (state.sessionId === sessionId) {
          await get().startNewChat();
        }
        return true;
      },

      archiveRemoteSession: async (sessionId) => {
        const result = await apiArchiveSession(sessionId);
        if (!result) return false;
        set({
          remoteSessionList: patchRemoteList(get().remoteSessionList, sessionId, {
            archived: true,
            status: "archived",
          }),
        });
        return true;
      },

      restoreRemoteSession: async (sessionId) => {
        const result = await apiRestoreSession(sessionId);
        if (!result) return false;
        set({
          remoteSessionList: patchRemoteList(get().remoteSessionList, sessionId, {
            archived: false,
            status: "active",
            deleted: false,
          }),
        });
        return true;
      },

      favoriteRemoteSession: async (sessionId, favorite = true) => {
        const result = await apiFavoriteSession(sessionId, favorite);
        if (!result) return false;
        set({
          remoteSessionList: patchRemoteList(get().remoteSessionList, sessionId, {
            favorite: result.favorite ?? favorite,
          }),
        });
        return true;
      },

      duplicateRemoteSession: async (sessionId, title) => {
        const result = await apiDuplicateSession(sessionId, title);
        if (result) {
          await get().refreshRemoteSessions();
        }
        return result;
      },

      resetConversation: (options) =>
        set((state) => {
          const sessionsById = {
            ...state.sessionsById,
            [state.sessionId]: snapshotFromState({
              ...state,
              messages: [],
              charts: [],
              forecast: null,
              suggestions: [],
              hypotheses: [],
              activeAssistantId: null,
            }),
          };
          return {
            messages: [],
            charts: [],
            forecast: null,
            suggestions: [],
            hypotheses: [],
            activeAssistantId: null,
            loading: false,
            datasetName: options?.keepDataset ? state.datasetName : "",
            filePath: options?.keepDataset ? state.filePath : "",
            sessionsById,
          };
        }),

      clearDataset: () => set({ datasetName: "", filePath: "" }),

      setLoading: (value) => set({ loading: value }),
    }),
    {
      name: "analytics-copilot-session",
      // Backend is source of truth for chat history — only keep active session identity
      partialize: (state) => ({
        sessionId: state.sessionId,
        datasetName: state.datasetName,
        filePath: state.filePath,
      }),
    }
  )
);
