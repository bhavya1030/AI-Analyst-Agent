import axios from "axios";
import {
  AssistantResponse,
  SessionDetail,
  SessionListResponse,
  SessionSearchResponse,
  SessionSummary,
  UploadResponse,
} from "@/types";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
});

// Optional multi-user header (Phase 8); defaults to anonymous on server.
const USER_HEADER = process.env.NEXT_PUBLIC_USER_ID;
if (USER_HEADER) {
  api.defaults.headers.common["X-User-Id"] = USER_HEADER;
}

export async function askQuestion(question: string, sessionId: string, filePath?: string) {
  const response = await api.get<AssistantResponse>("/v1/ask", {
    params: {
      question,
      session_id: sessionId,
      file_path: filePath,
    },
  });
  return response.data;
}

export async function uploadDataset(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await api.post<UploadResponse>("/upload", formData);
  return response.data;
}

/** List sessions (detail summaries) from backend — source of truth. */
export async function fetchSessions(options?: {
  limit?: number;
  offset?: number;
  includeArchived?: boolean;
  q?: string;
}): Promise<SessionSummary[]> {
  try {
    const response = await api.get<SessionListResponse>("/sessions", {
      params: {
        detail: true,
        limit: options?.limit ?? 100,
        offset: options?.offset ?? 0,
        include_archived: options?.includeArchived ?? true,
        include_deleted: false,
        sort_by: "updated_at",
        order: "desc",
        q: options?.q || undefined,
      },
    });
    return response.data?.items || [];
  } catch {
    return [];
  }
}

/** Recent sessions. */
export async function fetchRecentSessions(limit = 20): Promise<SessionSummary[]> {
  try {
    const response = await api.get<SessionListResponse>("/sessions/recent", {
      params: { limit, include_archived: false },
    });
    return response.data?.items || [];
  } catch {
    // Fallback to list
    return fetchSessions({ limit, includeArchived: false });
  }
}

/** Full-text search across sessions. */
export async function searchSessions(
  q: string,
  options?: { limit?: number; offset?: number }
): Promise<SessionSearchResponse> {
  try {
    const response = await api.get<SessionSearchResponse>("/sessions/search", {
      params: {
        q,
        limit: options?.limit ?? 30,
        offset: options?.offset ?? 0,
        include_archived: true,
      },
    });
    return (
      response.data || {
        query: q,
        total: 0,
        limit: options?.limit ?? 30,
        offset: 0,
        items: [],
      }
    );
  } catch {
    return { query: q, total: 0, limit: options?.limit ?? 30, offset: 0, items: [] };
  }
}

/** Full session restore payload. */
export async function fetchSessionDetail(sessionId: string): Promise<SessionDetail | null> {
  try {
    const response = await api.get<SessionDetail>(
      `/sessions/${encodeURIComponent(sessionId)}`
    );
    return response.data;
  } catch {
    return null;
  }
}

export async function createSession(payload?: {
  title?: string;
  session_id?: string;
  dataset_name?: string;
  dataset_path?: string;
  dataset_url?: string;
  tags?: string[];
}): Promise<SessionSummary | null> {
  try {
    const response = await api.post<SessionSummary>("/sessions", payload || {});
    return response.data;
  } catch {
    return null;
  }
}

/** Partial update (dataset binding, title, flags). */
export async function updateSession(
  sessionId: string,
  payload: {
    title?: string;
    dataset_id?: string;
    dataset_name?: string;
    dataset_path?: string;
    dataset_url?: string;
    dataset_topic?: string;
    tags?: string[];
    favorite?: boolean;
    pinned?: boolean;
    status?: "active" | "archived";
  }
): Promise<SessionSummary | null> {
  try {
    const response = await api.put<SessionSummary>(
      `/sessions/${encodeURIComponent(sessionId)}`,
      payload
    );
    return response.data;
  } catch {
    return null;
  }
}

export async function renameSession(sessionId: string, title: string): Promise<SessionSummary | null> {
  try {
    const response = await api.post<SessionSummary>(
      `/sessions/${encodeURIComponent(sessionId)}/rename`,
      { title }
    );
    return response.data;
  } catch {
    return null;
  }
}

export async function deleteSession(
  sessionId: string,
  hard = false
): Promise<boolean> {
  try {
    await api.delete(`/sessions/${encodeURIComponent(sessionId)}`, {
      params: { hard },
    });
    return true;
  } catch {
    return false;
  }
}

export async function archiveSession(sessionId: string): Promise<SessionSummary | null> {
  try {
    const response = await api.post<SessionSummary>(
      `/sessions/${encodeURIComponent(sessionId)}/archive`
    );
    return response.data;
  } catch {
    return null;
  }
}

export async function restoreSession(sessionId: string): Promise<SessionSummary | null> {
  try {
    const response = await api.post<SessionSummary>(
      `/sessions/${encodeURIComponent(sessionId)}/restore`
    );
    return response.data;
  } catch {
    return null;
  }
}

export async function favoriteSession(
  sessionId: string,
  favorite = true
): Promise<SessionSummary | null> {
  try {
    const response = await api.post<SessionSummary>(
      `/sessions/${encodeURIComponent(sessionId)}/favorite`,
      { favorite }
    );
    return response.data;
  } catch {
    return null;
  }
}

export async function pinSession(
  sessionId: string,
  pinned = true
): Promise<SessionSummary | null> {
  try {
    const response = await api.post<SessionSummary>(
      `/sessions/${encodeURIComponent(sessionId)}/pin`,
      { pinned }
    );
    return response.data;
  } catch {
    return null;
  }
}

export async function duplicateSession(
  sessionId: string,
  title?: string
): Promise<SessionSummary | null> {
  try {
    const response = await api.post<SessionSummary>(
      `/sessions/${encodeURIComponent(sessionId)}/duplicate`,
      { title, include_messages: true, include_artifacts: true }
    );
    return response.data;
  } catch {
    return null;
  }
}

/** Export full session bundle (JSON). */
export async function exportSession(sessionId: string): Promise<Record<string, unknown> | null> {
  try {
    const response = await api.get<Record<string, unknown>>(
      `/sessions/${encodeURIComponent(sessionId)}/export`
    );
    return response.data;
  } catch {
    return null;
  }
}

/** Import a previously exported session bundle. */
export async function importSession(payload: {
  bundle: Record<string, unknown>;
  session_id?: string;
  title?: string;
}): Promise<SessionSummary | null> {
  try {
    const response = await api.post<SessionSummary>("/sessions/import", payload);
    return response.data;
  } catch {
    return null;
  }
}
