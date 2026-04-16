import Sidebar from "@/components/sidebar/Sidebar";
import ChatWindow from "@/components/chat/ChatWindow";
import ChatInput from "@/components/chat/ChatInput";
import SuggestionsPanel from "@/components/suggestions/SuggestionsPanel";
import HypothesisPanel from "@/components/hypotheses/HypothesisPanel";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-[1700px] gap-4 px-4 py-4">
        <Sidebar />

        <div className="flex min-h-screen flex-1 flex-col gap-4">
          <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-800 dark:bg-slate-900">
            <h1 className="text-2xl font-semibold">Analytics Copilot</h1>
            <p className="mt-2 max-w-2xl text-slate-600 dark:text-slate-400">
              Ask questions about your dataset, explore charts, forecasts, and hypotheses in one conversational workspace.
            </p>
          </div>

          <div className="grid flex-1 gap-4 xl:grid-cols-[1fr_320px]">
            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-800 dark:bg-slate-900">
              <ChatWindow />
              <ChatInput />
            </div>

            <div className="flex flex-col gap-4">
              <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-800 dark:bg-slate-900">
                <SuggestionsPanel />
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-800 dark:bg-slate-900">
                <HypothesisPanel />
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
