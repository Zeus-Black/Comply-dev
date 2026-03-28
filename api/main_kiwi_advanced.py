"""
Comply API v2 — FastAPI avec streaming SSE, sessions, et recherche hybride
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import AsyncGenerator, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from kiwi_rag_advanced import ComplyRAG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Comply API",
    version="2.0.0",
    description="Assistant IA pour les Junior-Entreprises françaises",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rag: Optional[ComplyRAG] = None


# ─────────────────────────────────────────────────────────────────────────────
# Schémas Pydantic
# ─────────────────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000, description="Question pour Comply")
    session_id: Optional[str] = Field(None, description="ID de session pour l'historique")
    model: Optional[str] = Field(None, description="Modèle à utiliser (claude-sonnet-4-6, mistral-large-latest, ...)")


class ChatResponse(BaseModel):
    answer: str
    source: str = Field(..., description="rag | web | ticket")
    confidence: float
    documents_found: int
    session_id: Optional[str]
    model: str


class SessionResponse(BaseModel):
    session_id: str


# Rétrocompatibilité avec l'ancien format
class LegacyQuestion(BaseModel):
    question: str
    debug: bool = False
    context_type: str = "auto"


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    global rag
    logger.info("Démarrage de Comply API v2...")

    def init_rag():
        global rag
        try:
            rag = ComplyRAG()
            stats = rag.get_stats()
            logger.info(f"RAG prêt : {stats['total_documents']} documents indexés")
        except Exception as exc:
            logger.error(f"Erreur initialisation RAG : {exc}")

    # Indexation en tâche de fond pour ne pas bloquer le démarrage
    import threading
    thread = threading.Thread(target=init_rag, daemon=True)
    thread.start()
    logger.info("Indexation lancée en arrière-plan — l'API répond déjà")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints principaux
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/chat", response_model=ChatResponse, summary="Chat avec Comply")
async def chat(req: ChatRequest):
    """Endpoint principal de chat (réponse complète)."""
    if rag is None:
        raise HTTPException(503, detail="Comply est en cours d'initialisation, réessayez dans quelques secondes...")

    sid = req.session_id or rag.new_session()
    result = rag.answer(req.question, session_id=sid, model=req.model)
    return ChatResponse(
        answer=result["answer"],
        source=result["source"],
        confidence=result["confidence"],
        documents_found=result["documents_found"],
        session_id=sid,
        model=result["model"],
    )


@app.post("/chat/stream", summary="Chat en streaming (SSE)")
async def chat_stream(req: ChatRequest):
    """Endpoint streaming — envoie les tokens au fur et à mesure."""
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")

    sid = req.session_id or rag.new_session()

    async def event_generator() -> AsyncGenerator[bytes, None]:
        # Envoie d'abord le session_id
        yield f"data: {json.dumps({'type': 'session', 'session_id': sid})}\n\n".encode()

        try:
            async for chunk in rag.stream_answer(req.question, session_id=sid, model=req.model):
                payload = json.dumps({"type": "token", "text": chunk})
                yield f"data: {payload}\n\n".encode()
        except Exception as exc:
            logger.error(f"Erreur streaming : {exc}")
            error_payload = json.dumps({"type": "error", "message": str(exc)})
            yield f"data: {error_payload}\n\n".encode()

        yield b"data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gestion des sessions
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/sessions/new", response_model=SessionResponse)
async def new_session():
    """Crée une nouvelle session de conversation."""
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    sid = rag.new_session()
    return SessionResponse(session_id=sid)


@app.get("/sessions/{session_id}/history")
async def get_history(session_id: str):
    """Récupère l'historique d'une session."""
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    history = rag.get_session_history(session_id)
    return {"session_id": session_id, "messages": history}


@app.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """Efface l'historique d'une session."""
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    rag.clear_session(session_id)
    return {"status": "ok", "session_id": session_id}


# ─────────────────────────────────────────────────────────────────────────────
# Administration
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/reindex", summary="Réindexation complète")
async def reindex(background_tasks: BackgroundTasks):
    """Relance l'indexation complète en arrière-plan."""
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    background_tasks.add_task(rag.reindex)
    return {"status": "reindexation_en_cours"}


@app.get("/stats", summary="Statistiques du système")
async def stats():
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    return rag.get_stats()


@app.get("/health", summary="Santé du service")
async def health():
    docs = rag.get_stats()["total_documents"] if rag else 0
    return {
        "status": "ok",
        "service": "Comply API",
        "version": "2.0.0",
        "rag_ready": rag is not None,
        "documents_indexed": docs,
        "indexing": rag is None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Rétrocompatibilité (anciens endpoints)
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/ask")
async def ask_legacy(req: LegacyQuestion):
    """Endpoint de rétrocompatibilité (Slack bot existant)."""
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    result = rag.answer(req.question)
    return {
        "question": req.question,
        "answer": result["answer"],
        "context_found": result["documents_found"] > 0,
        "query_type": result["source"],
        "sources_count": result["documents_found"],
        "kiwi_specialized": result["source"] == "rag",
        "status": "success",
    }


if __name__ == "__main__":
    uvicorn.run("main_kiwi_advanced:app", host="0.0.0.0", port=8000, reload=True)
