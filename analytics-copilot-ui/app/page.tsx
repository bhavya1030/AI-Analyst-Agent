"use client";

import { useEffect } from "react";
import AnalysisCanvas from "@/components/workspace/AnalysisCanvas";
import AiCopilotPanel from "@/components/workspace/AiCopilotPanel";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";

export default function HomePage() {
  const rehydrateActiveSession = useChatStore((s) => s.rehydrateActiveSession);
  const refreshRemoteSessions = useChatStore((s) => s.refreshRemoteSessions);
  const mobileChatOpen = useUiStore((s) => s.mobileChatOpen);
  const setMobileChatOpen = useUiStore((s) => s.setMobileChatOpen);

  useEffect(() => {
    void rehydrateActiveSession();
    void refreshRemoteSessions({ includeArchived: true });
  }, [rehydrateActiveSession, refreshRemoteSessions]);

  return (
    <div className="mx-auto flex h-full max-w-[1800px] flex-col gap-0 p-0 md:gap-3 md:p-3 lg:p-4">
      {/* Desktop: 70 / 30 split */}
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,7fr)_minmax(320px,3fr)]">
        <div className="min-h-0 px-3 pt-3 md:px-0 md:pt-0">
          <AnalysisCanvas />
        </div>
        <div className="hidden min-h-0 lg:block">
          <AiCopilotPanel />
        </div>
      </div>

      {/* Mobile chat sheet */}
      {mobileChatOpen ? (
        <div className="fixed inset-0 z-50 flex flex-col bg-black/45 backdrop-blur-sm lg:hidden animate-fade-in">
          <div className="mt-auto h-[92vh] w-full">
            <AiCopilotPanel mobile onClose={() => setMobileChatOpen(false)} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
