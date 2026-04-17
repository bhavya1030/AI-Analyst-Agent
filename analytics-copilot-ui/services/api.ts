import axios from "axios";
import { AssistantResponse, UploadResponse } from "@/types";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
});

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

export async function fetchSessions() {
  try {
    const response = await api.get<string[]>("/sessions");
    return response.data;
  } catch {
    return [];
  }
}
