"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import { Send, Paperclip, X, ChevronDown } from "lucide-react";
import Header, { MODELS } from "./Header";
import Sidebar from "./Sidebar";
import MessageBubble from "./MessageBubble";
import { Conversation, Message, UploadedFile } from "@/types";
import { streamChat, uploadDocument } from "@/lib/api";

const WELCOME_MESSAGE: Message = {
  id: "welcome",
  role: "assistant",
  content: `Bonjour ! Je suis **Comply**, l'assistant IA de SEPEFREI.

Je peux vous aider avec :
- **Kiwi Légal** — réglementation, statuts, contrats, comptabilité
- **Kiwi Formation** — formations, e-learnings, ressources pédagogiques
- **Kiwi Services** — partenaires et services
- **Kiwi RSE** — responsabilité sociétale, développement durable
- **Documents** — guides, tutoriels, modèles de documents

Vous pouvez aussi joindre des documents pour que je les analyse.

Comment puis-je vous aider aujourd'hui ?`,
  timestamp: new Date(),
  source: "rag",
};

const SUGGESTED_QUESTIONS = [
  "Comment facturer une étude ?",
  "Quelles sont les obligations légales d'une JE ?",
  "Comment recruter des intervenants ?",
  "Qu'est-ce que la TVA pour une JE ?",
];

export default function ChatInterface() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedModel, setSelectedModel] = useState(MODELS[0].id);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<UploadedFile[]>([]);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback((smooth = true) => {
    messagesEndRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "instant" });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);

  const handleScroll = () => {
    const el = chatContainerRef.current;
    if (el) {
      setShowScrollBtn(el.scrollHeight - el.scrollTop - el.clientHeight > 100);
    }
  };

  const createNewConversation = useCallback(() => {
    const id = uuidv4();
    const conv: Conversation = {
      id,
      title: "Nouvelle conversation",
      messages: [{ ...WELCOME_MESSAGE, id: uuidv4(), timestamp: new Date() }],
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    setConversations((prev) => [conv, ...prev]);
    setActiveConvId(id);
    setMessages(conv.messages);
    setSessionId(null);
    setAttachments([]);
    setInput("");
    setTimeout(() => inputRef.current?.focus(), 100);
    return id;
  }, []);

  useEffect(() => { createNewConversation(); }, []);

  const selectConversation = useCallback((id: string) => {
    const conv = conversations.find((c) => c.id === id);
    if (conv) {
      setActiveConvId(id);
      setMessages(conv.messages);
      setSessionId(conv.sessionId || null);
    }
  }, [conversations]);

  const deleteConversation = useCallback((id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (activeConvId === id) createNewConversation();
  }, [activeConvId, createNewConversation]);

  const updateConversation = useCallback((msgs: Message[], sid?: string) => {
    if (!activeConvId) return;
    setConversations((prev) =>
      prev.map((c) => {
        if (c.id !== activeConvId) return c;
        const firstUser = msgs.find((m) => m.role === "user");
        return {
          ...c,
          messages: msgs,
          updatedAt: new Date(),
          sessionId: sid || c.sessionId,
          title: firstUser?.content.slice(0, 50) || c.title,
        };
      })
    );
  }, [activeConvId]);

  const handleFileUpload = async (files: FileList | null) => {
    if (!files) return;
    for (const file of Array.from(files)) {
      if (file.size > 10 * 1024 * 1024) { alert(`${file.name} trop volumineux (max 10MB)`); continue; }
      try {
        const content = await uploadDocument(file);
        setAttachments((prev) => [...prev, { id: uuidv4(), name: file.name, type: file.type, size: file.size, content }]);
      } catch (e) { console.error(e); }
    }
  };

  const sendMessage = useCallback(async (questionOverride?: string) => {
    const question = (questionOverride ?? input).trim();
    if (!question || isLoading) return;

    const fileContext = attachments.map((f) => `[Document: ${f.name}]\n${f.content?.slice(0, 5000)}`).join("\n\n---\n\n");
    const fullQuestion = fileContext ? `${question}\n\n---\nDocuments joints :\n${fileContext}` : question;

    const userMsg: Message = {
      id: uuidv4(), role: "user", content: question,
      timestamp: new Date(), attachments: attachments.length > 0 ? [...attachments] : undefined,
    };
    const assistantMsg: Message = { id: uuidv4(), role: "assistant", content: "", timestamp: new Date(), isStreaming: true };
    const newMessages = [...messages, userMsg, assistantMsg];
    setMessages(newMessages);
    setInput("");
    setAttachments([]);
    setIsLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;
    let sid = sessionId;
    let fullContent = "";

    try {
      for await (const chunk of streamChat({ question: fullQuestion, session_id: sid || undefined, model: selectedModel }, controller.signal)) {
        if (chunk.type === "session" && chunk.session_id) { sid = chunk.session_id; setSessionId(sid); }
        else if (chunk.type === "token" && chunk.text) {
          fullContent += chunk.text;
          setMessages((prev) => prev.map((m) => m.id === assistantMsg.id ? { ...m, content: fullContent, isStreaming: true } : m));
        } else if (chunk.type === "done") break;
        else if (chunk.type === "error") { fullContent = "Une erreur s'est produite. Veuillez réessayer."; break; }
      }
    } catch (err: any) {
      if (err.name !== "AbortError") fullContent = "Erreur de connexion à l'API. Vérifiez que le serveur est démarré sur le port 8000.";
    } finally {
      const finalMsgs = newMessages.map((m) =>
        m.id === assistantMsg.id ? { ...m, content: fullContent || "Désolé, je n'ai pas pu générer de réponse.", isStreaming: false, source: "rag" as const } : m
      );
      setMessages(finalMsgs);
      updateConversation(finalMsgs, sid || undefined);
      setIsLoading(false);
      abortRef.current = null;
      scrollToBottom();
    }
  }, [input, messages, isLoading, sessionId, attachments, updateConversation, scrollToBottom]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50 overflow-hidden">
      <Header onToggleSidebar={() => setSidebarOpen((p) => !p)} sidebarOpen={sidebarOpen} selectedModel={selectedModel} onModelChange={setSelectedModel} />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          open={sidebarOpen}
          conversations={conversations}
          activeId={activeConvId}
          onSelectConversation={selectConversation}
          onNewConversation={createNewConversation}
          onDeleteConversation={deleteConversation}
        />

        <main className="flex-1 flex flex-col overflow-hidden relative">
          {/* Messages */}
          <div ref={chatContainerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 py-6">
            <div className="max-w-3xl mx-auto">
              {messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)}

              {messages.length === 1 && (
                <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {SUGGESTED_QUESTIONS.map((q) => (
                    <button key={q} onClick={() => sendMessage(q)}
                      className="text-left px-4 py-3 bg-white rounded-xl border border-comply-100 hover:border-comply-400 hover:bg-comply-50 transition-all text-sm text-gray-700 shadow-sm">
                      {q}
                    </button>
                  ))}
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {showScrollBtn && (
            <button onClick={() => scrollToBottom()} className="absolute bottom-24 right-6 bg-comply-600 text-white rounded-full p-2 shadow-lg hover:bg-comply-700 transition-colors z-10">
              <ChevronDown className="w-4 h-4" />
            </button>
          )}

          {/* Attachments */}
          {attachments.length > 0 && (
            <div className="max-w-3xl mx-auto w-full px-4">
              <div className="flex flex-wrap gap-2 pb-2">
                {attachments.map((f) => (
                  <div key={f.id} className="flex items-center gap-1.5 bg-comply-50 border border-comply-200 rounded-lg px-3 py-1.5 text-xs text-comply-700">
                    <span className="max-w-[120px] truncate">📎 {f.name}</span>
                    <button onClick={() => setAttachments((p) => p.filter((a) => a.id !== f.id))} className="text-comply-500 hover:text-red-500">
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Input */}
          <div className="border-t border-gray-200 bg-white px-4 py-3 shadow-sm">
            <div className="max-w-3xl mx-auto">
              <div className="flex items-end gap-2 bg-white border-2 border-gray-200 focus-within:border-comply-400 rounded-2xl px-4 py-2.5 transition-colors">
                <input ref={fileInputRef} type="file" className="hidden" multiple
                  accept=".pdf,.txt,.md,.doc,.docx,.csv,.json"
                  onChange={(e) => handleFileUpload(e.target.files)} />
                <button onClick={() => fileInputRef.current?.click()}
                  className="flex-shrink-0 p-1.5 text-gray-400 hover:text-comply-600 transition-colors rounded-lg hover:bg-comply-50"
                  title="Joindre un document" disabled={isLoading}>
                  <Paperclip className="w-4 h-4" />
                </button>

                <textarea ref={inputRef} value={input} onChange={handleInputChange} onKeyDown={handleKeyDown}
                  placeholder="Posez votre question à Comply... (Entrée pour envoyer)"
                  className="flex-1 resize-none bg-transparent outline-none text-sm text-gray-800 placeholder-gray-400 min-h-[24px] max-h-40 leading-relaxed py-0.5"
                  rows={1} disabled={isLoading} />

                {isLoading ? (
                  <button onClick={() => { abortRef.current?.abort(); setIsLoading(false); }}
                    className="flex-shrink-0 p-2 bg-red-500 hover:bg-red-600 text-white rounded-xl transition-colors" title="Arrêter">
                    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
                  </button>
                ) : (
                  <button onClick={() => sendMessage()} disabled={!input.trim() && attachments.length === 0}
                    className="flex-shrink-0 p-2 bg-comply-600 hover:bg-comply-700 disabled:bg-gray-200 disabled:cursor-not-allowed text-white rounded-xl transition-colors shadow-sm">
                    <Send className="w-4 h-4" />
                  </button>
                )}
              </div>
              <p className="text-center text-xs text-gray-400 mt-2">
                Comply peut faire des erreurs — vérifiez les informations importantes.
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
