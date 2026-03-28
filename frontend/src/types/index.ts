export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  source?: "rag" | "web" | "ticket";
  confidence?: number;
  documentsFound?: number;
  isStreaming?: boolean;
  attachments?: UploadedFile[];
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
  sessionId?: string;
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
  file_context?: string;
  model?: string;
}

export interface StreamChunk {
  type: "session" | "token" | "error" | "done";
  text?: string;
  session_id?: string;
  message?: string;
}
