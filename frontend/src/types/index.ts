export interface AuthUser {
  id: string;
  email: string;
  name: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  source?: "rag" | "web" | "ticket" | "cache";
  model_used?: string;
  isStreaming?: boolean;
  attachments?: UploadedFile[];
}

export interface Conversation {
  id: string;
  title: string;
  session_id: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
  message_count?: number;
}

export interface UploadedFile {
  id: string;
  name: string;
  type: string;
  size: number;
  content?: string;
}

export interface ChatRequest {
  question: string;
  session_id?: string;
  model?: string;
}

export interface StreamChunk {
  type: "session" | "token" | "error" | "done";
  text?: string;
  session_id?: string;
  message?: string;
}
