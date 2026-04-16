export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  text: string;
  charts?: ChartPayload[];
  forecast?: ForecastResult | null;
  hypotheses?: string[];
  suggestions?: string[];
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
}

export interface AssistantResponse extends AssistantPayload {
  question?: string;
}

export interface UploadResponse {
  message: string;
  file_path: string;
}

export interface SessionState {
  sessionId: string;
  datasetName: string;
  messages: ChatMessage[];
  charts: ChartPayload[];
  forecast: ForecastResult | null;
  suggestions: string[];
  hypotheses: string[];
}
