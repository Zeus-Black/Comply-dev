"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check, Globe, Database, AlertCircle } from "lucide-react";
import { useState } from "react";
import { Message } from "@/types";

interface MessageBubbleProps {
  message: Message;
}

function SourceBadge({ source }: { source?: string }) {
  if (!source) return null;

  const config = {
    rag: { icon: <Database className="w-3 h-3" />, label: "Base Kiwi", color: "text-comply-700 bg-comply-50 border-comply-200" },
    web: { icon: <Globe className="w-3 h-3" />, label: "Recherche web", color: "text-blue-700 bg-blue-50 border-blue-200" },
    ticket: { icon: <AlertCircle className="w-3 h-3" />, label: "Support CNJE", color: "text-amber-700 bg-amber-50 border-amber-200" },
  }[source] || { icon: null, label: source, color: "text-gray-600 bg-gray-50 border-gray-200" };

  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border font-medium ${config.color}`}>
      {config.icon}
      {config.label}
    </span>
  );
}

function AttachmentBadge({ name }: { name: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs bg-comply-50 border border-comply-200 rounded-lg px-2.5 py-1.5 text-comply-700 mb-2">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="w-3.5 h-3.5" strokeWidth={2}>
        <path strokeLinecap="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
      </svg>
      {name}
    </div>
  );
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <div className="flex justify-end mb-4 message-enter">
        <div className="max-w-[75%]">
          {message.attachments?.map((f) => (
            <AttachmentBadge key={f.id} name={f.name} />
          ))}
          <div className="bg-comply-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          </div>
          <div className="text-right mt-1">
            <span className="text-xs text-gray-400">
              {message.timestamp.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 mb-4 message-enter">
      {/* Avatar Comply */}
      <div className="flex-shrink-0 w-8 h-8 bg-comply-600 rounded-xl flex items-center justify-center shadow-sm mt-0.5">
        <svg viewBox="0 0 24 24" fill="none" stroke="white" className="w-4 h-4" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>

      <div className="max-w-[80%] flex-1">
        <div className="bg-white rounded-2xl rounded-tl-sm border border-gray-100 shadow-sm px-4 py-3">
          {message.isStreaming && !message.content ? (
            /* Typing indicator */
            <div className="flex items-center gap-1.5 py-1">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          ) : (
            <div className="prose prose-sm max-w-none text-gray-800">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Metadata */}
        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          <span className="text-xs text-gray-400">
            {message.timestamp.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
          </span>

          {message.source && !message.isStreaming && (
            <SourceBadge source={message.source} />
          )}

          {message.documentsFound !== undefined && message.documentsFound > 0 && (
            <span className="text-xs text-gray-400">
              {message.documentsFound} source{message.documentsFound > 1 ? "s" : ""}
            </span>
          )}

          {!message.isStreaming && message.content && (
            <button
              onClick={handleCopy}
              className="ml-auto p-1 text-gray-400 hover:text-comply-600 transition-colors rounded"
              title="Copier"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-comply-500" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
