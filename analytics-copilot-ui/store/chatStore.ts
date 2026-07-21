import { create } from "zustand";
import { persist } from "zustand/middleware";
import { loadSessionState } from "@/utils/localStorage";
import {
  ChatMessage,
  ForecastResult,
  HistoryEntry,
  SessionDetail,
  SessionSnapshot,
  SessionState,
} from "@/types";

interface ChatStore extends SessionState {
  loading: boolean;
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
  /** Persist the active chat into sessionsById */
  saveCurrentSession: () => void;
  /** Open a session in the center Analyze chat block */
  openSession: (sessionId: string, options?: { focusMessageId?: string; detail?: SessionDetail | null }) => void;
  /** Apply a backend session detail when no local snapshot exists */
  hydrateFromSessionDetail: (detail: SessionDetail) => void;
  startNewChat: () => void;
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
    activeAssistantId:
      snapshot.activeAssistantId || lastAssistant?.id || null,
  };
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessionId: `session-${Date.now()}`,
      datasetName: loadSessionState("analytics-copilot-dataset", ""),
      filePath: loadSessionState("analytics-copilot-filepath", ""),
      messages: [],
      charts: [],
      forecast: null,
      suggestions: [],
      hypotheses: [],
      history: [],
      activeAssistantId: null,
      sessionsById: {},
      loading: false,

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
          patch.history = [entry, ...state.history.filter((h) => h.id !== entry.id)].slice(0, 50);
        }

        // Keep per-session snapshot in sync so history reopen works.
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
        set({ history: [entry, ...get().history.filter((h) => h.id !== entry.id)].slice(0, 50) }),

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

      openSession: (sessionId, options) => {
        const state = get();
        if (!sessionId) return;

        // Always snapshot the chat we are leaving.
        const leaving = snapshotFromState(state);
        const sessionsById = {
          ...(state.sessionsById || {}),
          [state.sessionId]: leaving,
        };

        // Already on this session — just focus a message if requested.
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

        const cached = sessionsById[sessionId];
        if (cached && cached.messages?.length) {
          set({
            sessionsById,
            ...applySnapshot(cached),
          });
          if (options?.focusMessageId) {
            const msgs = cached.messages;
            const assistant = msgs.find(
              (m, idx) =>
                m.role === "assistant" && msgs[idx - 1]?.id === options.focusMessageId
            );
            if (assistant) {
              set({ activeAssistantId: assistant.id });
            }
          }
          return;
        }

        // No local cache — open empty shell; caller may hydrate from API.
        if (options?.detail) {
          const hydrated = messagesFromDetail(options.detail);
          const snap: SessionSnapshot = {
            sessionId,
            datasetName: options.detail.dataset_topic || "",
            filePath: options.detail.dataset_path || "",
            messages: hydrated,
            charts: [],
            forecast: null,
            suggestions: [],
            hypotheses: [],
            activeAssistantId: hydrated.find((m) => m.role === "assistant")?.id || null,
            updatedAt: Date.now(),
          };
          set({
            sessionsById: { ...sessionsById, [sessionId]: snap },
            ...applySnapshot(snap),
          });
          return;
        }

        set({
          sessionsById: {
            ...sessionsById,
            [sessionId]: sessionsById[sessionId] || emptySnapshot(sessionId),
          },
          sessionId,
          datasetName: sessionsById[sessionId]?.datasetName || "",
          filePath: sessionsById[sessionId]?.filePath || "",
          messages: sessionsById[sessionId]?.messages || [],
          charts: sessionsById[sessionId]?.charts || [],
          forecast: sessionsById[sessionId]?.forecast || null,
          suggestions: sessionsById[sessionId]?.suggestions || [],
          hypotheses: sessionsById[sessionId]?.hypotheses || [],
          activeAssistantId: sessionsById[sessionId]?.activeAssistantId || null,
        });
      },

      hydrateFromSessionDetail: (detail) => {
        const state = get();
        const sessionId = detail.session_id;
        const existing = state.sessionsById[sessionId];
        // Prefer richer local cache if it already has a multi-turn chat.
        if (existing && existing.messages.length > 1) {
          set({
            ...applySnapshot(existing),
            sessionsById: state.sessionsById,
          });
          return;
        }

        const messages = messagesFromDetail(detail);
        const snap: SessionSnapshot = {
          sessionId,
          datasetName: detail.dataset_topic || existing?.datasetName || "",
          filePath: detail.dataset_path || existing?.filePath || "",
          messages: existing?.messages?.length ? existing.messages : messages,
          charts: existing?.charts || [],
          forecast: existing?.forecast || null,
          suggestions: existing?.suggestions || [],
          hypotheses: existing?.hypotheses || [],
          activeAssistantId:
            existing?.activeAssistantId ||
            messages.find((m) => m.role === "assistant")?.id ||
            null,
          updatedAt: Date.now(),
        };

        set({
          sessionsById: { ...state.sessionsById, [sessionId]: snap },
          ...applySnapshot(snap),
        });
      },

      startNewChat: () => {
        const state = get();
        const sessionsById = {
          ...state.sessionsById,
          [state.sessionId]: snapshotFromState(state),
        };
        const newId = `session-${Date.now()}`;
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
          // Keep dataset for convenience unless user clears it
          datasetName: state.datasetName,
          filePath: state.filePath,
        });
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
      partialize: (state) => ({
        sessionId: state.sessionId,
        datasetName: state.datasetName,
        filePath: state.filePath,
        messages: state.messages,
        charts: state.charts,
        forecast: state.forecast,
        suggestions: state.suggestions,
        hypotheses: state.hypotheses,
        history: state.history,
        activeAssistantId: state.activeAssistantId,
        sessionsById: state.sessionsById,
      }),
    }
  )
);

function messagesFromDetail(detail: SessionDetail): ChatMessage[] {
  const messages: ChatMessage[] = [];
  const ts = Date.now();
  if (detail.last_query) {
    messages.push({
      id: `restored-user-${detail.session_id}`,
      role: "user",
      text: detail.last_query,
      timestamp: ts - 1000,
    });
  }
  if (detail.last_insight) {
    messages.push({
      id: `restored-assistant-${detail.session_id}`,
      role: "assistant",
      text: detail.last_insight,
      timestamp: ts,
    });
  }
  if (!messages.length) {
    messages.push({
      id: `restored-empty-${detail.session_id}`,
      role: "assistant",
      text: `Opened session “${detail.session_id}”. ${
        detail.dataset_topic
          ? `Active topic: ${detail.dataset_topic}. `
          : ""
      }Ask a follow-up in the chat to continue analysis.`,
      timestamp: ts,
    });
  }
  return messages;
}
