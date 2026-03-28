"use client";

import { Plus, MessageSquare, Trash2, ChevronRight } from "lucide-react";
import { Conversation } from "@/types";

interface SidebarProps {
  open: boolean;
  conversations: Conversation[];
  activeId: string | null;
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
  onDeleteConversation: (id: string) => void;
}

export default function Sidebar({
  open,
  conversations,
  activeId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
}: SidebarProps) {
  return (
    <aside
      className={`
        flex flex-col bg-comply-950 text-white transition-all duration-300 ease-in-out overflow-hidden
        ${open ? "w-64" : "w-0"}
        border-r border-comply-900
      `}
    >
      {open && (
        <div className="flex flex-col h-full w-64">
          {/* Header sidebar */}
          <div className="p-4 border-b border-comply-800">
            <button
              onClick={onNewConversation}
              className="w-full flex items-center gap-2.5 bg-comply-600 hover:bg-comply-500 text-white rounded-xl px-4 py-2.5 font-medium text-sm transition-colors shadow-sm"
            >
              <Plus className="w-4 h-4" />
              Nouvelle conversation
            </button>
          </div>

          {/* Liste des conversations */}
          <div className="flex-1 overflow-y-auto py-2">
            {conversations.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <MessageSquare className="w-8 h-8 text-comply-700 mx-auto mb-2" />
                <p className="text-comply-600 text-xs">Aucune conversation</p>
              </div>
            ) : (
              <div className="space-y-0.5 px-2">
                {conversations.map((conv) => (
                  <div
                    key={conv.id}
                    className={`
                      group flex items-center gap-2 rounded-lg px-3 py-2.5 cursor-pointer transition-colors
                      ${activeId === conv.id
                        ? "bg-comply-800 text-white"
                        : "text-comply-300 hover:bg-comply-900 hover:text-white"
                      }
                    `}
                    onClick={() => onSelectConversation(conv.id)}
                  >
                    <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
                    <span className="flex-1 text-xs truncate leading-tight">
                      {conv.title || "Nouvelle conversation"}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteConversation(conv.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-red-400 transition-all"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer sidebar */}
          <div className="p-4 border-t border-comply-800">
            <div className="flex items-center gap-2 text-comply-500 text-xs">
              <div className="w-1.5 h-1.5 bg-comply-600 rounded-full" />
              <span>Comply v2.0 · SEPEFREI</span>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
