"""
Tests — Endpoints chat, sessions, santé et statistiques
"""

import json
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# /health
# ─────────────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client, inject_rag):
        inject_rag.get_stats.return_value = {"total_documents": 1898}
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.0.0"
        assert data["rag_ready"] is True
        assert data["documents_indexed"] == 1898

    def test_health_no_rag(self, client):
        import main_kiwi_advanced as app_module
        app_module.rag = None
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["rag_ready"] is False
        assert data["documents_indexed"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# /stats
# ─────────────────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_returns_rag_stats(self, client, inject_rag):
        inject_rag.get_stats.return_value = {
            "total_documents": 42,
            "chunks": 210,
            "sessions": 3,
        }
        resp = client.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_documents"] == 42
        assert data["chunks"] == 210

    def test_stats_rag_not_ready(self, client):
        import main_kiwi_advanced as app_module
        app_module.rag = None
        resp = client.get("/stats")
        assert resp.status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
# /sessions
# ─────────────────────────────────────────────────────────────────────────────

class TestSessions:
    def test_new_session(self, client, inject_rag):
        inject_rag.new_session.return_value = "sess-xyz-999"
        resp = client.post("/sessions/new")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "sess-xyz-999"

    def test_get_session_history_empty(self, client, inject_rag):
        inject_rag.get_session_history.return_value = []
        resp = client.get("/sessions/sess-123/history")
        assert resp.status_code == 200
        assert resp.json()["messages"] == []
        assert resp.json()["session_id"] == "sess-123"

    def test_get_session_history_with_messages(self, client, inject_rag):
        inject_rag.get_session_history.return_value = [
            {"role": "user", "content": "Bonjour"},
            {"role": "assistant", "content": "Bonjour !"},
        ]
        resp = client.get("/sessions/sess-abc/history")
        assert resp.status_code == 200
        msgs = resp.json()["messages"]
        assert len(msgs) == 2

    def test_delete_session(self, client, inject_rag):
        resp = client.delete("/sessions/sess-to-clear")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        inject_rag.clear_session.assert_called_with("sess-to-clear")

    def test_sessions_503_when_rag_not_ready(self, client):
        import main_kiwi_advanced as app_module
        app_module.rag = None
        assert client.post("/sessions/new").status_code == 503
        assert client.get("/sessions/x/history").status_code == 503
        assert client.delete("/sessions/x").status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
# /chat (non-streaming)
# ─────────────────────────────────────────────────────────────────────────────

class TestChat:
    def test_chat_success(self, client, inject_rag):
        inject_rag.answer.return_value = {
            "answer": "La TVA est à 20%.",
            "source": "rag",
            "confidence": 0.9,
            "documents_found": 5,
            "model": "claude-sonnet-4-6",
        }
        inject_rag.new_session.return_value = "sess-chat-001"
        resp = client.post("/chat", json={"question": "Quelle est la TVA ?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "La TVA est à 20%."
        assert data["source"] == "rag"
        assert data["confidence"] == 0.9
        assert data["documents_found"] == 5
        assert "session_id" in data

    def test_chat_with_existing_session(self, client, inject_rag):
        resp = client.post("/chat", json={
            "question": "Question de suivi",
            "session_id": "sess-existing",
        })
        assert resp.status_code == 200
        # La session fournie est utilisée
        call_args = inject_rag.answer.call_args
        assert call_args.kwargs.get("session_id") == "sess-existing" or \
               "sess-existing" in str(call_args)

    def test_chat_with_model_selection(self, client, inject_rag):
        resp = client.post("/chat", json={
            "question": "Bonjour",
            "model": "claude-opus-4-6",
        })
        assert resp.status_code == 200

    def test_chat_empty_question_fails(self, client):
        resp = client.post("/chat", json={"question": ""})
        assert resp.status_code == 422

    def test_chat_question_too_long_fails(self, client):
        resp = client.post("/chat", json={"question": "x" * 4001})
        assert resp.status_code == 422

    def test_chat_503_when_rag_not_ready(self, client):
        import main_kiwi_advanced as app_module
        app_module.rag = None
        resp = client.post("/chat", json={"question": "Test"})
        assert resp.status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
# /chat/stream (SSE)
# ─────────────────────────────────────────────────────────────────────────────

class TestChatStream:
    def test_stream_returns_sse_content_type(self, client, inject_rag):
        resp = client.post(
            "/chat/stream",
            json={"question": "Qu'est-ce qu'une JE ?"},
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_stream_contains_session_event(self, client, inject_rag):
        inject_rag.new_session.return_value = "sess-stream-001"
        resp = client.post(
            "/chat/stream",
            json={"question": "Bonjour"},
        )
        assert resp.status_code == 200
        content = resp.text
        assert "sess-stream-001" in content

    def test_stream_contains_token_events(self, client, inject_rag):
        resp = client.post(
            "/chat/stream",
            json={"question": "Test streaming"},
        )
        content = resp.text
        # Le mock envoie "Réponse ", "simulée ", "en streaming."
        assert "Réponse" in content
        assert "streaming" in content

    def test_stream_ends_with_done(self, client, inject_rag):
        resp = client.post(
            "/chat/stream",
            json={"question": "Test"},
        )
        assert "[DONE]" in resp.text

    def test_stream_503_when_rag_not_ready(self, client):
        import main_kiwi_advanced as app_module
        app_module.rag = None
        resp = client.post("/chat/stream", json={"question": "Test"})
        assert resp.status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
# /ask (endpoint legacy)
# ─────────────────────────────────────────────────────────────────────────────

class TestAskLegacy:
    def test_ask_success(self, client, inject_rag):
        inject_rag.answer.return_value = {
            "answer": "Voici la réponse.",
            "source": "rag",
            "confidence": 0.8,
            "documents_found": 2,
            "model": "claude-sonnet-4-6",
        }
        resp = client.post("/ask", json={"question": "Qu'est-ce que la CNJE ?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["answer"] == "Voici la réponse."
        assert data["context_found"] is True
        assert data["sources_count"] == 2

    def test_ask_no_documents_found(self, client, inject_rag):
        inject_rag.answer.return_value = {
            "answer": "Je ne sais pas.",
            "source": "web",
            "confidence": 0.1,
            "documents_found": 0,
            "model": "claude-sonnet-4-6",
        }
        resp = client.post("/ask", json={"question": "Question hors sujet"})
        assert resp.status_code == 200
        assert resp.json()["context_found"] is False

    def test_ask_503_when_rag_not_ready(self, client):
        import main_kiwi_advanced as app_module
        app_module.rag = None
        resp = client.post("/ask", json={"question": "Test"})
        assert resp.status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
# /reindex
# ─────────────────────────────────────────────────────────────────────────────

class TestReindex:
    def test_reindex_triggers_background(self, client, inject_rag):
        resp = client.post("/reindex")
        assert resp.status_code == 200
        assert resp.json()["status"] == "reindexation_en_cours"
        inject_rag.cache_flush.assert_called()

    def test_reindex_503_when_rag_not_ready(self, client):
        import main_kiwi_advanced as app_module
        app_module.rag = None
        resp = client.post("/reindex")
        assert resp.status_code == 503
