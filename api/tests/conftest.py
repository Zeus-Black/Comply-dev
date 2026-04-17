"""
Comply — Configuration globale des tests pytest
"""

from __future__ import annotations

import os

# ── Variables d'environnement à injecter AVANT tout import de l'app ──────────
os.environ.setdefault("NEXTAUTH_SECRET", "test-secret-comply-jest")
os.environ.setdefault("CLAUDE_API_KEY", "fake-api-key-tests")
os.environ.setdefault("MISTRAL_API_KEY", "")
os.environ.setdefault("DEEPSEEK_API_KEY", "")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("ENABLE_WEB_SEARCH", "false")
os.environ.setdefault("REDIS_URL", "redis://localhost:6399")  # port inexistant

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# ── Base de données en mémoire partagée (StaticPool) ─────────────────────────
from database import Base, get_db

_TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_TEST_ENGINE)
Base.metadata.create_all(bind=_TEST_ENGINE)


def _override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


# ── RAG mocké ──────────────────────────────────────────────────────────────────

async def _fake_stream_answer(question: str, session_id=None, model=None):
    """Async generator simulant le streaming du RAG."""
    for token in ["Réponse ", "simulée ", "en streaming."]:
        yield token


def _build_mock_rag() -> MagicMock:
    mock = MagicMock()
    mock._sessions = {}
    mock.new_session.return_value = "sess-test-001"
    mock.get_stats.return_value = {
        "total_documents": 42,
        "chunks": 210,
        "sessions": 0,
        "index_size_kb": 0,
        "cache_entries": 0,
    }
    mock.get_session_history.return_value = []
    mock.clear_session.return_value = None
    mock.reindex.return_value = None
    mock.cache_flush.return_value = None
    mock.answer.return_value = {
        "answer": "Réponse de test.",
        "source": "rag",
        "confidence": 0.85,
        "documents_found": 3,
        "model": "claude-sonnet-4-6",
    }
    mock.stream_answer = _fake_stream_answer
    return mock


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def mock_rag():
    """RAG mocké réutilisé pour toute la session."""
    return _build_mock_rag()


@pytest.fixture(autouse=True)
def reset_db():
    """Réinitialise les tables avant chaque test pour l'isolation."""
    Base.metadata.drop_all(bind=_TEST_ENGINE)
    Base.metadata.create_all(bind=_TEST_ENGINE)
    yield


@pytest.fixture(autouse=True)
def inject_rag(mock_rag):
    """Injecte le RAG mocké dans l'app avant chaque test."""
    import main_kiwi_advanced as app_module
    app_module.rag = mock_rag
    yield mock_rag
    # Remet None pour signaler qu'on est hors contexte de test
    app_module.rag = None


@pytest.fixture(scope="session")
def app():
    """Instance FastAPI avec les overrides de dépendances pour les tests."""
    import main_kiwi_advanced as app_module

    # Patch ComplyRAG pour éviter l'init au démarrage
    with patch("main_kiwi_advanced.ComplyRAG"):
        app_module.app.dependency_overrides[get_db] = _override_get_db
        yield app_module.app
        app_module.app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def client(app):
    """TestClient réutilisé pour toute la session."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def db():
    """Session DB de test (rollback après chaque test)."""
    session = _TestingSession()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def registered_user(client):
    """Crée et retourne un utilisateur de test via l'API."""
    resp = client.post("/auth/register", json={
        "email": "alice@je.fr",
        "name": "Alice Dupont",
        "password": "securepass123",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
def auth_headers(registered_user):
    """Headers HTTP avec token Bearer pour l'utilisateur de test."""
    return {"Authorization": f"Bearer {registered_user['token']}"}


@pytest.fixture
def second_user(client):
    """Second utilisateur pour tester l'isolation des données."""
    resp = client.post("/auth/register", json={
        "email": "bob@je.fr",
        "name": "Bob Martin",
        "password": "securepass456",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data, {"Authorization": f"Bearer {data['token']}"}
