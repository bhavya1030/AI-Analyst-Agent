export type Role = "user" | "assistant";

export interface AcquisitionOption {
  type?: string;
  label: string;
  how?: string;
}

export interface ChatMessage {
  id: string;
  role: Role;
  text: string;
  charts?: ChartPayload[];
  forecast?: ForecastResult | null;
  hypotheses?: string[];
  suggestions?: string[];
  timestamp?: number;
  needsUserData?: boolean;
  acquisitionOptions?: AcquisitionOption[];
  relatedDatasets?: Array<Record<string, any>>;
  discovery?: Record<string, any> | null;
  source?: string;
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
  needs_user_data?: boolean;
  data_acquisition_options?: AcquisitionOption[];
  dataset_discovery?: Record<string, any>;
  search_queries?: string[];
  source?: string;
  product_promise?: string;
}

export interface AssistantResponse extends AssistantPayload {
  question?: string;
  /** Single chart object sometimes returned by the API instead of charts[] */
  chart?: any;
  session_id?: string;
  message_id?: string;
}

export interface UploadResponse {
  message: string;
  file_path: string;
}

/** Backend chat message (Phase 1+ persistence) */
export interface BackendChatMessage {
  id: string;
  seq: number;
  role: string;
  content: string;
  created_at?: string;
  payload?: Record<string, any> | null;
  is_summarized?: boolean;
  summary_group_id?: string | null;
}

/** Full restore payload from GET /sessions/{id} */
export interface SessionDetail {
  session_id: string;
  title?: string;
  created_at?: string;
  updated_at?: string;
  last_activity_at?: string;
  dataset_id?: string;
  dataset_name?: string;
  dataset_path?: string;
  dataset_url?: string;
  dataset_topic?: string;
  current_dataset?: Record<string, any> | null;
  last_used_columns?: string[];
  status?: string;
  favorite?: boolean;
  archived?: boolean;
  deleted?: boolean;
  pinned?: boolean;
  pin_order?: number | null;
  tags?: string[];
  message_count?: number;
  user_id?: string;
  conversation_summary?: string;

  chat_history?: BackendChatMessage[];
  generated_charts?: any[];
  forecast_results?: any[];
  analysis_results?: any[];
  eda_outputs?: any[];
  artifacts?: Array<{
    id: string;
    kind: string;
    title?: string;
    content?: any;
    meta?: Record<string, any> | null;
    message_id?: string | null;
  }>;

  // Legacy flat fields
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

export interface SessionSummary {
  session_id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
  last_activity_at?: string;
  dataset_id?: string | null;
  dataset_name?: string | null;
  dataset_topic?: string | null;
  status?: string;
  favorite?: boolean;
  archived?: boolean;
  deleted?: boolean;
  pinned?: boolean;
  pin_order?: number | null;
  message_count?: number;
  tags?: string[];
  last_query?: string | null;
  conversation_summary?: string | null;
  user_id?: string;
}

export interface SessionListResponse {
  items: SessionSummary[];
  total: number;
  limit: number;
  offset: number;
  sort_by?: string;
  order?: string;
  filters?: Record<string, any>;
}

export interface SessionSearchHit {
  session_id: string;
  title: string;
  score?: number;
  rank?: number;
  snippet?: string;
  matched_fields?: string[];
  highlights?: Record<string, string>;
  dataset_topic?: string | null;
  dataset_name?: string | null;
  message_count?: number;
  updated_at?: string;
  last_activity_at?: string;
  favorite?: boolean;
  archived?: boolean;
  pinned?: boolean;
  tags?: string[];
  status?: string;
}

export interface SessionSearchResponse {
  query: string;
  match_query?: string;
  total: number;
  limit: number;
  offset: number;
  engine?: string;
  items: SessionSearchHit[];
}

export interface HistoryEntry {
  id: string;
  title: string;
  sessionId: string;
  preview: string;
  timestamp: number;
  datasetName?: string;
  messageId?: string;
}

/** In-memory snapshot for active session UI (not durable source of truth) */
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
  title?: string;
  favorite?: boolean;
  archived?: boolean;
  pinned?: boolean;
  status?: string;
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
  /** Ephemeral UI cache only — backend is source of truth */
  sessionsById: Record<string, SessionSnapshot>;
  /** Server session list */
  remoteSessionList: SessionSummary[];
  /**
   * Monotonic analysis request sequence.
   * Guards against out-of-order responses and restore races.
   */
  analysisSeq: number;
  /** In-flight request id (null when idle) */
  pendingRequestId: string | null;
  /** True only during initial mount rehydrate — never after user starts analyzing */
  bootstrapping: boolean;
}
