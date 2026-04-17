"""
Comply API v2 — FastAPI avec streaming SSE, sessions, multi-utilisateurs et conversations persistantes
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator, List, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import Conversation, Message, User, get_db, init_db
from auth import create_token, get_current_user, get_optional_user, hash_password, verify_password
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
    question: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None
    model: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    source: str
    confidence: float
    documents_found: int
    session_id: Optional[str]
    model: str


class SessionResponse(BaseModel):
    session_id: str


class LegacyQuestion(BaseModel):
    question: str
    debug: bool = False
    context_type: str = "auto"


# Auth schemas
class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3)
    name: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    id: str
    email: str
    name: str
    token: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime


# Conversation schemas
class ConversationCreate(BaseModel):
    title: Optional[str] = "Nouvelle conversation"


class ConversationRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class ConversationSummary(BaseModel):
    id: str
    title: str
    session_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class MessageCreate(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)
    source: Optional[str] = "rag"
    model_used: Optional[str] = ""


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    source: str
    model_used: str
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    session_id: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse]


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    global rag

    # Init DB (crée les tables)
    init_db()
    logger.info("Base de données initialisée")

    def init_rag():
        global rag
        try:
            rag = ComplyRAG()
            stats = rag.get_stats()
            logger.info(f"RAG prêt : {stats['total_documents']} documents indexés")
        except Exception as exc:
            logger.error(f"Erreur initialisation RAG : {exc}")

    import threading
    threading.Thread(target=init_rag, daemon=True).start()
    logger.info("Indexation RAG lancée en arrière-plan")


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=AuthResponse, summary="Créer un compte")
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email.lower()).first():
        raise HTTPException(400, detail="Cette adresse email est déjà utilisée")

    user = User(
        id=str(uuid.uuid4()),
        email=req.email.lower().strip(),
        name=req.name.strip(),
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.email)
    return AuthResponse(id=user.id, email=user.email, name=user.name, token=token)


@app.post("/auth/login", response_model=AuthResponse, summary="Se connecter")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not verify_password(req.password, user.hashed_password):
        import asyncio
        await asyncio.sleep(0.5)  # anti-bruteforce
        raise HTTPException(401, detail="Email ou mot de passe incorrect")

    token = create_token(user.id, user.email)
    return AuthResponse(id=user.id, email=user.email, name=user.name, token=token)


@app.get("/auth/me", response_model=UserResponse, summary="Profil utilisateur")
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        created_at=current_user.created_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Conversations
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/conversations", response_model=List[ConversationSummary], summary="Lister les conversations")
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [
        ConversationSummary(
            id=c.id,
            title=c.title,
            session_id=c.session_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=len(c.messages),
        )
        for c in convs
    ]


@app.post("/conversations", response_model=ConversationSummary, summary="Créer une conversation")
async def create_conversation(
    req: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")

    session_id = rag.new_session()
    conv = Conversation(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        title=req.title or "Nouvelle conversation",
        session_id=session_id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    return ConversationSummary(
        id=conv.id,
        title=conv.title,
        session_id=conv.session_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
    )


@app.get("/conversations/{conv_id}", response_model=ConversationDetail, summary="Détail d'une conversation")
async def get_conversation(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(404, detail="Conversation introuvable")

    # Restaurer la session RAG depuis les messages DB si absente en mémoire
    if rag and conv.session_id not in rag._sessions:
        history = [
            {"role": m.role, "content": m.content}
            for m in conv.messages[-10:]
        ]
        if history:
            rag._sessions[conv.session_id] = history

    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        session_id=conv.session_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                source=m.source,
                model_used=m.model_used,
                created_at=m.created_at,
            )
            for m in conv.messages
        ],
    )


@app.delete("/conversations/{conv_id}", summary="Supprimer une conversation")
async def delete_conversation(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(404, detail="Conversation introuvable")

    if rag:
        rag.clear_session(conv.session_id)

    db.delete(conv)
    db.commit()
    return {"ok": True}


@app.patch("/conversations/{conv_id}", summary="Renommer une conversation")
async def rename_conversation(
    conv_id: str,
    req: ConversationRename,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(404, detail="Conversation introuvable")

    conv.title = req.title
    conv.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@app.post("/conversations/{conv_id}/messages", response_model=MessageResponse, summary="Ajouter un message")
async def add_message(
    conv_id: str,
    req: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(404, detail="Conversation introuvable")

    msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv_id,
        role=req.role,
        content=req.content,
        source=req.source or "rag",
        model_used=req.model_used or "",
    )
    db.add(msg)

    # Mettre à jour titre et date
    conv.updated_at = datetime.utcnow()
    if conv.title == "Nouvelle conversation" and req.role == "user":
        conv.title = req.content[:60]

    db.commit()
    db.refresh(msg)

    return MessageResponse(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        source=msg.source,
        model_used=msg.model_used,
        created_at=msg.created_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Chat (compatible Slack bot + extension)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse, summary="Chat avec Comply")
async def chat(req: ChatRequest):
    if rag is None:
        raise HTTPException(503, detail="Comply est en cours d'initialisation...")
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
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    sid = req.session_id or rag.new_session()

    async def event_generator() -> AsyncGenerator[bytes, None]:
        yield f"data: {json.dumps({'type': 'session', 'session_id': sid})}\n\n".encode()
        try:
            async for chunk in rag.stream_answer(req.question, session_id=sid, model=req.model):
                yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n".encode()
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Upload de documents
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/upload", summary="Extraire le texte d'un document")
async def upload_document(file: UploadFile = File(...)):
    content_bytes = await file.read()
    filename = file.filename or "document"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

    if len(content_bytes) > 20 * 1024 * 1024:
        raise HTTPException(413, detail="Fichier trop volumineux (max 20 MB)")

    try:
        if ext == "pdf":
            from pypdf import PdfReader
            from io import BytesIO
            reader = PdfReader(BytesIO(content_bytes))
            text = "\n\n".join(p.extract_text() or "" for p in reader.pages).strip()
        elif ext == "docx":
            from docx import Document
            from io import BytesIO
            doc = Document(BytesIO(content_bytes))
            text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        else:
            text = content_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(400, detail=f"Extraction impossible : {exc}")

    if not text.strip():
        raise HTTPException(422, detail="Aucun texte extrait du document")

    return {"filename": filename, "extension": ext, "text": text[:50000], "chars": len(text), "truncated": len(text) > 50000}


# ─────────────────────────────────────────────────────────────────────────────
# Sync Notion / Drive
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/sync/notion", summary="Synchroniser Notion")
async def sync_notion(background_tasks: BackgroundTasks):
    from config import NOTION_API_KEY
    if not NOTION_API_KEY:
        raise HTTPException(400, detail="NOTION_API_KEY non configurée dans .env")
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")

    def do_sync():
        try:
            from connector_notion import sync_notion_to_json
            from config import DATA_DIR
            count = sync_notion_to_json(NOTION_API_KEY, f"{DATA_DIR}/notion.json")
            logger.info(f"Notion sync : {count} pages")
            rag.cache_flush()
            rag.reindex()
        except Exception as exc:
            logger.error(f"Erreur sync Notion : {exc}")

    background_tasks.add_task(do_sync)
    return {"status": "sync_notion_en_cours"}


@app.post("/sync/drive", summary="Synchroniser Google Drive")
async def sync_drive(background_tasks: BackgroundTasks):
    from config import GOOGLE_DRIVE_SERVICE_ACCOUNT, GOOGLE_DRIVE_TOKEN_FILE
    if not GOOGLE_DRIVE_SERVICE_ACCOUNT and not GOOGLE_DRIVE_TOKEN_FILE:
        raise HTTPException(400, detail="Credentials Google Drive manquantes")
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")

    def do_sync():
        try:
            from connector_drive import sync_drive_to_json
            from config import DATA_DIR, GOOGLE_DRIVE_SERVICE_ACCOUNT, GOOGLE_DRIVE_TOKEN_FILE, GOOGLE_DRIVE_FOLDER_ID
            count = sync_drive_to_json(
                service_account_json=GOOGLE_DRIVE_SERVICE_ACCOUNT,
                token_file=GOOGLE_DRIVE_TOKEN_FILE,
                folder_id=GOOGLE_DRIVE_FOLDER_ID,
                output_path=f"{DATA_DIR}/drive.json",
            )
            logger.info(f"Drive sync : {count} fichiers")
            rag.cache_flush()
            rag.reindex()
        except Exception as exc:
            logger.error(f"Erreur sync Drive : {exc}")

    background_tasks.add_task(do_sync)
    return {"status": "sync_drive_en_cours"}


# ─────────────────────────────────────────────────────────────────────────────
# Sessions / Stats / Health
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/sessions/new", response_model=SessionResponse)
async def new_session():
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    return SessionResponse(session_id=rag.new_session())


@app.get("/sessions/{session_id}/history")
async def get_history(session_id: str):
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    return {"session_id": session_id, "messages": rag.get_session_history(session_id)}


@app.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    rag.clear_session(session_id)
    return {"status": "ok"}


@app.post("/reindex")
async def reindex(background_tasks: BackgroundTasks):
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    rag.cache_flush()
    background_tasks.add_task(rag.reindex)
    return {"status": "reindexation_en_cours"}


@app.get("/stats")
async def stats():
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    return rag.get_stats()


@app.get("/health")
async def health():
    docs = rag.get_stats()["total_documents"] if rag else 0
    return {"status": "ok", "version": "2.0.0", "rag_ready": rag is not None, "documents_indexed": docs}


@app.post("/ask")
async def ask_legacy(req: LegacyQuestion):
    if rag is None:
        raise HTTPException(503, detail="RAG non initialisé")
    result = rag.answer(req.question)
    return {
        "question": req.question,
        "answer": result["answer"],
        "context_found": result["documents_found"] > 0,
        "query_type": result["source"],
        "sources_count": result["documents_found"],
        "status": "success",
    }


if __name__ == "__main__":
    uvicorn.run("main_kiwi_advanced:app", host="0.0.0.0", port=8000, reload=True)
