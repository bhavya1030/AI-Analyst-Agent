/**
 * State synchronization regression tests.
 * Verifies request sequencing, canvas clear on begin, restore race guards.
 */

import { useChatStore } from "@/store/chatStore";
import type { ChatMessage } from "@/types";

function resetStore() {
  useChatStore.setState({
    sessionId: "test-session",
    datasetName: "India GDP",
    filePath: "/data/india_gdp.csv",
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
    analysisSeq: 0,
    pendingRequestId: null,
    bootstrapping: false,
  });
}

describe("analysis state synchronization", () => {
  beforeEach(() => {
    resetStore();
  });

  it("beginAnalysis clears canvas projection but keeps messages", () => {
    const india: ChatMessage = {
      id: "asst-india",
      role: "assistant",
      text: "India GDP analysis",
      charts: [{ id: "c1", type: "line", figure: { data: [] } }],
      timestamp: 1,
    };
    useChatStore.getState().addMessage({
      id: "user-1",
      role: "user",
      text: "Analyze India GDP",
      timestamp: 1,
    });
    useChatStore.getState().addMessage(india);

    expect(useChatStore.getState().charts.length).toBe(1);
    expect(useChatStore.getState().activeAssistantId).toBe("asst-india");

    useChatStore.getState().beginAnalysis("req-gold");

    const s = useChatStore.getState();
    expect(s.loading).toBe(true);
    expect(s.pendingRequestId).toBe("req-gold");
    expect(s.charts).toEqual([]);
    expect(s.forecast).toBeNull();
    expect(s.activeAssistantId).toBeNull();
    // Conversation history preserved
    expect(s.messages.length).toBe(2);
    expect(s.messages[1].text).toContain("India GDP");
  });

  it("completeAnalysis ignores stale request ids", () => {
    useChatStore.getState().beginAnalysis("req-1");
    useChatStore.getState().beginAnalysis("req-2"); // supersedes

    const stale: ChatMessage = {
      id: "asst-stale",
      role: "assistant",
      text: "Stale India result",
      charts: [{ id: "old", type: "bar", figure: {} }],
      timestamp: 2,
    };
    const ok = useChatStore.getState().completeAnalysis("req-1", stale);
    expect(ok).toBe(false);
    expect(useChatStore.getState().activeAssistantId).toBeNull();
    expect(useChatStore.getState().charts).toEqual([]);

    const fresh: ChatMessage = {
      id: "asst-gold",
      role: "assistant",
      text: "Gold prices analysis",
      charts: [{ id: "gold-c", type: "line", figure: { data: [1] } }],
      timestamp: 3,
    };
    const accepted = useChatStore.getState().completeAnalysis("req-2", fresh, {
      datasetName: "Gold prices",
      clearFilePath: true,
    });
    expect(accepted).toBe(true);
    const s = useChatStore.getState();
    expect(s.loading).toBe(false);
    expect(s.pendingRequestId).toBeNull();
    expect(s.activeAssistantId).toBe("asst-gold");
    expect(s.charts[0].id).toBe("gold-c");
    expect(s.datasetName).toBe("Gold prices");
    expect(s.filePath).toBe("");
  });

  it("hydrateFromSessionDetail does not overwrite while loading", () => {
    useChatStore.getState().beginAnalysis("req-live");
    useChatStore.getState().hydrateFromSessionDetail({
      session_id: "test-session",
      title: "Old",
      dataset_topic: "India GDP",
      dataset_path: "/old.csv",
      chat_history: [
        { id: "m1", seq: 1, role: "user", content: "old q" },
        { id: "m2", seq: 2, role: "assistant", content: "old answer" },
      ],
      message_count: 2,
    });
    // Still loading — restore rejected
    expect(useChatStore.getState().pendingRequestId).toBe("req-live");
    expect(useChatStore.getState().messages).toEqual([]);
  });

  it("hydrate works when idle", () => {
    useChatStore.getState().hydrateFromSessionDetail({
      session_id: "test-session",
      title: "Restored",
      dataset_topic: "Gold",
      dataset_path: "/gold.csv",
      chat_history: [
        { id: "m1", seq: 1, role: "user", content: "Analyze gold" },
        { id: "m2", seq: 2, role: "assistant", content: "Gold rose." },
      ],
      message_count: 2,
    });
    const s = useChatStore.getState();
    expect(s.messages.length).toBe(2);
    expect(s.datasetName).toMatch(/Gold/i);
    expect(s.filePath).toBe("/gold.csv");
    expect(s.loading).toBe(false);
  });

  it("failAnalysis only clears matching request", () => {
    useChatStore.getState().beginAnalysis("req-a");
    useChatStore.getState().beginAnalysis("req-b");
    useChatStore.getState().failAnalysis("req-a");
    // Still pending b
    expect(useChatStore.getState().loading).toBe(true);
    expect(useChatStore.getState().pendingRequestId).toBe("req-b");
    useChatStore.getState().failAnalysis("req-b", {
      id: "err",
      role: "assistant",
      text: "error",
      timestamp: 1,
    });
    expect(useChatStore.getState().loading).toBe(false);
    expect(useChatStore.getState().messages.some((m) => m.text === "error")).toBe(
      true
    );
  });
});
