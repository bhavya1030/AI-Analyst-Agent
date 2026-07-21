export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  text: string;
  charts?: ChartPayload[];
  forecast?: ForecastResult | null;
  hypotheses?: string[];
  suggestions?: string[];
  timestamp?: number;
}

export interface ChartPayload {
  id: string;
  type: string;
  figure: any;
  columns_used?: string[];
}

export interface ForecastResult {
  chart: any;
  values: Array<Record<string, any>>;
  explanation?: string;
}

export interface AssistantPayload {
  dataset_summary: Record<string, any>;
  dataset_topic: string;
  charts: ChartPayload[];
  forecast: Array<Record<string, any>>;
  forecast_chart: any;
  chart_explanation: string;
  detected_patterns: string[];
  hypotheses: string[];
  recommended_next_steps: string[];
  related_datasets: Array<Record<string, any>>;
  answer: string;
  dataset_url?: string;
  rows?: number;
  columns?: string[];
}

export interface AssistantResponse extends AssistantPayload {
  question?: string;
  /** Single chart object sometimes returned by the API instead of charts[] */
  chart?: any;
}

export interface UploadResponse {
  message: string;
  file_path: string;
}

export interface SessionDetail {
  session_id: string;
  dataset_path?: string;
  dataset_url?: string;
  dataset_topic?: string;
  last_query?: string;
  last_insight?: string;
  last_column?: string;
  last_columns?: string[];
  last_chart_type?: string;
  last_intent?: string;
  last_operation?: string;
  last_forecast_target?: string;
  eda_summary?: Record<string, any>;
}

export interface HistoryEntry {
  id: string;
  title: string;
  sessionId: string;
  preview: string;
  timestamp: number;
  datasetName?: string;
  /** Optional pointer to a user message id within that session */
  messageId?: string;
}

/** Full snapshot of one analyze session for reopen from history */
export interface SessionSnapshot {
  sessionId: string;
  datasetName: string;
  filePath: string;
  messages: ChatMessage[];
  charts: ChartPayload[];
  forecast: ForecastResult | null;
  suggestions: string[];
  hypotheses: string[];
  activeAssistantId: string | null;
  updatedAt: number;
}

export interface SessionState {
  sessionId: string;
  datasetName: string;
  /** Absolute path returned by /upload — sent as file_path on /ask */
  filePath: string;
  messages: ChatMessage[];
  charts: ChartPayload[];
  forecast: ForecastResult | null;
  suggestions: string[];
  hypotheses: string[];
  history: HistoryEntry[];
  activeAssistantId: string | null;
  /** Cached conversations keyed by session id */
  sessionsById: Record<string, SessionSnapshot>;
}
