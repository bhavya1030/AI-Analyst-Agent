/**
 * UI rendering / layout regression — no stale canvas, chat structure present.
 * @jest-environment jsdom
 */

import React from "react";
import { render, screen, act } from "@testing-library/react";
import { useChatStore } from "@/store/chatStore";
import AnalysisCanvas from "@/components/workspace/AnalysisCanvas";
import ChatWindow from "@/components/chat/ChatWindow";
import AiCopilotPanel from "@/components/workspace/AiCopilotPanel";

function resetStore() {
  useChatStore.setState({
    sessionId: "ui-test",
    datasetName: "India GDP",
    filePath: "/gdp.csv",
    messages: [
      {
        id: "u1",
        role: "user",
        text: "Analyze India GDP",
        timestamp: 1,
      },
      {
        id: "a1",
        role: "assistant",
        text: "India GDP rose steadily.",
        charts: [{ id: "c-india", type: "line", figure: { data: [] } }],
        timestamp: 2,
      },
    ],
    charts: [{ id: "c-india", type: "line", figure: { data: [] } }],
    forecast: null,
    suggestions: ["Forecast next"],
    hypotheses: ["Growth continues"],
    history: [],
    activeAssistantId: "a1",
    sessionsById: {},
    remoteSessionList: [],
    loading: false,
    sessionsLoading: false,
    analysisSeq: 0,
    pendingRequestId: null,
    bootstrapping: false,
  });
}

describe("UI state rendering sync", () => {
  beforeEach(() => {
    resetStore();
  });

  it("shows previous analysis when idle", () => {
    render(<AnalysisCanvas />);
    expect(screen.getByText(/India GDP rose steadily/i)).toBeInTheDocument();
    expect(screen.getByText(/Working set · India GDP/i)).toBeInTheDocument();
  });

  it("clears canvas content while loading (no stale India GDP)", () => {
    act(() => {
      useChatStore.getState().beginAnalysis("req-gold");
    });
    render(<AnalysisCanvas />);
    expect(screen.getByTestId("canvas-loading")).toBeInTheDocument();
    expect(screen.queryByText(/India GDP rose steadily/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/previous results are cleared/i)
    ).toBeInTheDocument();
  });

  it("renders gold analysis after completeAnalysis", () => {
    act(() => {
      useChatStore.getState().beginAnalysis("req-gold");
      useChatStore.getState().completeAnalysis(
        "req-gold",
        {
          id: "a-gold",
          role: "assistant",
          text: "Gold prices climbed over five years.",
          charts: [{ id: "c-gold", type: "line", figure: { data: [1] } }],
          timestamp: 3,
        },
        { datasetName: "Gold prices", clearFilePath: true }
      );
    });
    render(<AnalysisCanvas />);
    expect(screen.getByText(/Gold prices climbed/i)).toBeInTheDocument();
    expect(screen.queryByText(/India GDP rose steadily/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Working set · Gold prices/i)).toBeInTheDocument();
  });

  it("chat window has isolated scroll container", () => {
    render(<ChatWindow />);
    const win = screen.getByTestId("chat-window");
    expect(win.className).toMatch(/overflow-hidden/);
    expect(win.className).toMatch(/min-h-0/);
  });

  it("copilot panel keeps conversation and secondary panes separated", () => {
    const { container } = render(<AiCopilotPanel />);
    // Header + chat column + secondary region structure
    expect(container.querySelector("aside")).toBeTruthy();
    expect(screen.getByText("Conversation")).toBeInTheDocument();
    expect(screen.getByText("Suggestions")).toBeInTheDocument();
    expect(screen.getByText("Reasoning")).toBeInTheDocument();
  });
});
