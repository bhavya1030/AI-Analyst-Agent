import { create } from "zustand";
import { persist } from "zustand/middleware";
import { loadSessionState } from "@/utils/localStorage";
import { ChatMessage, ForecastResult, SessionState } from "@/types";

interface ChatStore extends SessionState {
  loading: boolean;
  addMessage: (message: ChatMessage) => void;
  setForecast: (forecast: ForecastResult | null) => void;
  setDatasetName: (name: string) => void;
  setSuggestions: (suggestions: string[]) => void;
  setHypotheses: (hypotheses: string[]) => void;
  setSessionId: (sessionId: string) => void;
  resetConversation: () => void;
  setLoading: (value: boolean) => void;
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessionId: "default",
      datasetName: loadSessionState("analytics-copilot-dataset", ""),
      messages: [],
      charts: [],
      forecast: null,
      suggestions: [],
      hypotheses: [],
      loading: false,
      addMessage: (message) => set({ messages: [...get().messages, message] }),
      setForecast: (forecast) => set({ forecast }),
      setDatasetName: (name) => set({ datasetName: name }),
      setSuggestions: (suggestions) => set({ suggestions }),
      setHypotheses: (hypotheses) => set({ hypotheses }),
      setSessionId: (sessionId) => set({ sessionId }),
      resetConversation: () =>
        set({
          messages: [],
          charts: [],
          forecast: null,
          suggestions: [],
          hypotheses: [],
          datasetName: "",
          loading: false,
        }),
      setLoading: (value) => set({ loading: value }),
    }),
    {
      name: "analytics-copilot-session",
      partialize: (state) => ({
        sessionId: state.sessionId,
        datasetName: state.datasetName,
        messages: state.messages,
        charts: state.charts,
        forecast: state.forecast,
        suggestions: state.suggestions,
        hypotheses: state.hypotheses,
      }),
    }
  )
);
