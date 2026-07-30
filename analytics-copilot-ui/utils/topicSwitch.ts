/**
 * Topic-switch detection (mirrors backend continuity/topic_switch).
 *
 * Upload India GDP → "Analyze IPL" must release the bound file.
 */

const OPERATION_TOKENS = new Set([
  "show",
  "plot",
  "chart",
  "graph",
  "visualize",
  "visualise",
  "draw",
  "histogram",
  "hist",
  "bar",
  "line",
  "scatter",
  "box",
  "heatmap",
  "correlation",
  "correlate",
  "corr",
  "distribution",
  "density",
  "forecast",
  "predict",
  "projection",
  "trend",
  "trends",
  "compare",
  "comparison",
  "versus",
  "vs",
  "analyze",
  "analyse",
  "analysis",
  "summarize",
  "summarise",
  "summary",
  "describe",
  "explain",
  "insight",
  "insights",
  "eda",
  "mean",
  "median",
  "std",
  "average",
  "max",
  "min",
  "count",
  "filter",
  "group",
  "by",
  "top",
  "bottom",
  "rank",
  "again",
  "another",
  "same",
  "more",
  "please",
  "help",
  "next",
  "previous",
  "past",
  "last",
  "years",
  "year",
  "months",
  "the",
  "and",
  "or",
  "of",
  "for",
  "to",
  "in",
  "on",
  "with",
  "from",
  "it",
  "this",
  "that",
  "them",
  "those",
  "data",
  "dataset",
  "column",
  "columns",
  "variable",
  "variables",
  "value",
  "values",
  "using",
  "use",
  "make",
  "create",
  "generate",
  "give",
  "display",
  "rate",
  "rates",
  "price",
  "prices",
  "over",
  "time",
  "series",
]);

const FOLLOW_UP_PHRASES = [
  "show histogram",
  "histogram",
  "show correlation",
  "correlation",
  "heatmap",
  "forecast",
  "predict",
  "plot it",
  "show it",
  "analyze it",
  "same dataset",
  "this data",
  "the data",
  "another chart",
  "distribution",
];

export function contentTokens(text: string): Set<string> {
  const tokens = (text.toLowerCase().match(/[a-z0-9]+/g) || []).filter(
    (t) => t.length > 2 && !OPERATION_TOKENS.has(t)
  );
  return new Set(tokens);
}

function pathTokens(path: string): Set<string> {
  if (!path) return new Set();
  const base = path.replace(/\\/g, "/").split("/").pop() || path;
  const stem = base.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
  return contentTokens(stem);
}

export function isFollowUpQuestion(text: string): boolean {
  const q = text.trim().toLowerCase();
  if (!q) return false;
  if (FOLLOW_UP_PHRASES.some((p) => q.includes(p))) return true;
  if (/\b(it|that|this|them|those|the same)\b/.test(q) && q.split(/\s+/).length <= 14) {
    return true;
  }
  const content = contentTokens(q);
  if (content.size === 0 && q.split(/\s+/).length <= 8) return true;
  return false;
}

/**
 * True when the user asks about a different subject than the bound upload/session.
 */
export function isTopicSwitch(
  question: string,
  datasetName: string,
  filePath: string
): boolean {
  if (!question.trim()) return false;
  if (!filePath && !datasetName) return false;

  const low = question.trim().toLowerCase();
  if (
    /(this file|my file|uploaded|this csv|this dataset|the uploaded)/.test(low)
  ) {
    return false;
  }

  const bound = new Set<string>([
    ...contentTokens(datasetName || ""),
    ...pathTokens(filePath || ""),
  ]);
  // "india" alone is weak — prefer metric tokens from filename
  const q = contentTokens(question);

  if (q.size === 0) {
    // Pure follow-up ops keep binding
    return false;
  }

  // Any content token overlap with bound dataset → same subject
  for (const t of q) {
    if (bound.has(t)) return false;
  }

  // Follow-up phrases with no subject overlap already handled; if we have
  // distinct subject nouns, switch.
  if (isFollowUpQuestion(question)) {
    // "forecast next 5 years" → no content tokens beyond ops → already returned false
    // "analyze IPL" is NOT a follow-up-only phrase
    const onlyOps =
      !/analyze|analyse|study|explore|dataset about|data on|find data/.test(low);
    if (onlyOps) return false;
  }

  // Distinct subject with analyze/study/explore → switch
  return true;
}

/** Whether to omit file_path from the ask request. */
export function shouldOmitFilePath(
  question: string,
  datasetName: string,
  filePath: string
): boolean {
  return isTopicSwitch(question, datasetName, filePath);
}
