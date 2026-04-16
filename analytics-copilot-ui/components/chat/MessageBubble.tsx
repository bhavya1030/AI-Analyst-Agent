"use client";

import { ChatMessage } from "@/types";
import ChartRenderer from "@/components/charts/ChartRenderer";
import ForecastPanel from "@/components/forecast/ForecastPanel";
import HypothesisPanel from "@/components/hypotheses/HypothesisPanel";
import SuggestionsPanel from "@/components/suggestions/SuggestionsPanel";

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isAssistant = message.role === "assistant";

  return (
    <div className={`flex ${isAssistant ? "justify-start" : "justify-end"}`}>
      <div className={`max-w-[85%] rounded-3xl border p-4 shadow-sm ${isAssistant ? "bg-slate-100 border-slate-200 text-slate-900 dark:bg-slate-950 dark:border-slate-800 dark:text-slate-100" : "bg-sky-600 border-sky-700 text-white"}`}>
        <p className="whitespace-pre-wrap text-sm leading-7">{message.text}</p>

        {message.charts?.length ? (
          <div className="mt-4 space-y-4">
            {message.charts.map((chart) => (
              <ChartRenderer key={chart.id} chart={chart} />
            ))}
          </div>
        ) : null}

        {message.forecast ? <ForecastPanel forecast={message.forecast} /> : null}
        {message.hypotheses?.length ? <HypothesisPanel hypotheses={message.hypotheses} /> : null}
        {message.suggestions?.length ? <SuggestionsPanel suggestions={message.suggestions} /> : null}
      </div>
    </div>
  );
}
