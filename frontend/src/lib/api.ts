import { ChatRequest, Conversation, Message, StreamChunk } from "@/types";
import { getToken } from "./auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Helpers ───────────────────────────────────────────────────────────────────

function jsonHeaders(): Record<string, string> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Erreur ${res.status}` }));
    throw new Error(err.detail || `Erreur ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Streaming chat ────────────────────────────────────────────────────────────

export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal
): AsyncGenerator<StreamChunk> {
  const response = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) throw new Error(`API error: ${response.status}`);

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6).trim();
        if (data === "[DONE]") { yield { type: "done" }; return; }
        try { yield JSON.parse(data) as StreamChunk; } catch {}
      }
    }
  }
}

// ── Conversations ─────────────────────────────────────────────────────────────

export async function fetchConversations(): Promise<Conversation[]> {
  const res = await fetch(`${API_URL}/conversations`, { headers: jsonHeaders() });
  const data = await handleResponse<any[]>(res);
  return data.map((c) => ({
    id: c.id,
    title: c.title,
    session_id: c.session_id,
    messages: [],
    createdAt: new Date(c.created_at),
    updatedAt: new Date(c.updated_at),
    message_count: c.message_count,
  }));
}

export async function createConversation(title = "Nouvelle conversation"): Promise<Conversation> {
  const res = await fetch(`${API_URL}/conversations`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ title }),
  });
  const data = await handleResponse<any>(res);
  return {
    id: data.id,
    title: data.title,
    session_id: data.session_id,
    messages: [],
    createdAt: new Date(data.created_at),
    updatedAt: new Date(data.updated_at),
  };
}

export async function fetchConversation(id: string): Promise<Conversation> {
  const res = await fetch(`${API_URL}/conversations/${id}`, { headers: jsonHeaders() });
  const data = await handleResponse<any>(res);
  return {
    id: data.id,
    title: data.title,
    session_id: data.session_id,
    createdAt: new Date(data.created_at),
    updatedAt: new Date(data.updated_at),
    messages: data.messages.map((m: any): Message => ({
      id: m.id,
      role: m.role,
      content: m.content,
      timestamp: new Date(m.created_at),
      source: m.source,
      model_used: m.model_used,
    })),
  };
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/conversations/${id}`, {
    method: "DELETE",
    headers: jsonHeaders(),
  });
  await handleResponse(res);
}

export async function renameConversation(id: string, title: string): Promise<void> {
  const res = await fetch(`${API_URL}/conversations/${id}`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify({ title }),
  });
  await handleResponse(res);
}

export async function saveMessage(
  convId: string,
  role: "user" | "assistant",
  content: string,
  source = "rag",
  model_used = ""
): Promise<Message> {
  const res = await fetch(`${API_URL}/conversations/${convId}/messages`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ role, content, source, model_used }),
  });
  const data = await handleResponse<any>(res);
  return {
    id: data.id,
    role: data.role,
    content: data.content,
    timestamp: new Date(data.created_at),
    source: data.source,
    model_used: data.model_used,
  };
}

// ── Upload document ───────────────────────────────────────────────────────────

const TEXT_EXTENSIONS = new Set(["txt", "md", "csv", "json"]);
const API_UPLOAD_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

function getExtension(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() ?? "";
}

export async function uploadDocument(file: File): Promise<string> {
  const ext = getExtension(file.name);
  const needsServer = API_UPLOAD_TYPES.has(file.type) || ext === "pdf" || ext === "docx";

  if (needsServer) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_URL}/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Erreur upload" }));
      throw new Error(err.detail);
    }
    const result = await res.json();
    return result.text as string;
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target?.result as string);
    reader.onerror = reject;
    reader.readAsText(file);
  });
}
