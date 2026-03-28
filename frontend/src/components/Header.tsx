"use client";

import Image from "next/image";
import { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";

export const MODELS = [
  { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", provider: "Anthropic" },
  { id: "mistral-large-latest", label: "Mistral Large", provider: "Mistral" },
  { id: "mistral-small-latest", label: "Mistral Small", provider: "Mistral" },
];

interface HeaderProps {
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
  selectedModel: string;
  onModelChange: (model: string) => void;
}

export default function Header({ onToggleSidebar, sidebarOpen, selectedModel, onModelChange }: HeaderProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const current = MODELS.find((m) => m.id === selectedModel) ?? MODELS[0];

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <header className="h-14 bg-white border-b border-comply-100 flex items-center px-4 gap-3 z-20 shadow-sm">
      <button onClick={onToggleSidebar}
        className="p-2 rounded-lg hover:bg-comply-50 transition-colors text-comply-600">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="w-5 h-5" strokeWidth={2}>
          <path strokeLinecap="round" d={sidebarOpen ? "M18 6L6 18M6 6l12 12" : "M4 6h16M4 12h16M4 18h16"} />
        </svg>
      </button>

      <div className="flex items-center gap-2">
        <Image
          src="/comply.png"
          alt="Comply"
          width={32}
          height={32}
          className="rounded-lg shadow-sm object-contain"
          priority
        />
        <span className="font-bold text-comply-700 text-lg tracking-tight">Comply</span>
        <span className="text-xs bg-comply-100 text-comply-700 px-2 py-0.5 rounded-full font-medium hidden sm:inline">
          SEPEFREI · Beta
        </span>
      </div>

      <div className="flex-1" />

      {/* Sélecteur de modèle */}
      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen((p) => !p)}
          className="flex items-center gap-2 text-xs text-comply-700 bg-comply-50 hover:bg-comply-100 px-3 py-1.5 rounded-full border border-comply-200 transition-colors font-medium"
        >
          <span className="w-1.5 h-1.5 bg-comply-500 rounded-full animate-pulse" />
          {current.label}
          <ChevronDown className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>

        {open && (
          <div className="absolute right-0 mt-1 w-52 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden z-50">
            {MODELS.map((m) => (
              <button
                key={m.id}
                onClick={() => { onModelChange(m.id); setOpen(false); }}
                className={`w-full text-left px-4 py-2.5 text-sm flex items-center justify-between transition-colors
                  ${m.id === selectedModel ? "bg-comply-50 text-comply-700 font-medium" : "text-gray-700 hover:bg-gray-50"}`}
              >
                <span>{m.label}</span>
                <span className="text-xs text-gray-400">{m.provider}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </header>
  );
}
