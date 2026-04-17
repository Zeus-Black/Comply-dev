"""
Tests — Conversations (CRUD complet)
"""

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def create_conv(client, headers, title="Nouvelle conversation"):
    resp = client.post("/conversations", json={"title": title}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Lister les conversations
# ─────────────────────────────────────────────────────────────────────────────

class TestListConversations:
    def test_list_empty_for_new_user(self, client, auth_headers):
        resp = client.get("/conversations", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_requires_auth(self, client):
        resp = client.get("/conversations")
        assert resp.status_code == 401

    def test_list_returns_own_conversations(self, client, auth_headers):
        create_conv(client, auth_headers, "Conv A")
        create_conv(client, auth_headers, "Conv B")
        resp = client.get("/conversations", headers=auth_headers)
        assert resp.status_code == 200
        titles = [c["title"] for c in resp.json()]
        assert "Conv A" in titles
        assert "Conv B" in titles

    def test_list_ordered_by_updated_desc(self, client, auth_headers):
        create_conv(client, auth_headers, "Première")
        create_conv(client, auth_headers, "Dernière")
        resp = client.get("/conversations", headers=auth_headers)
        convs = resp.json()
        # La plus récente apparaît en premier
        assert convs[0]["title"] == "Dernière"

    def test_list_isolation_between_users(self, client, auth_headers, second_user):
        _, bob_headers = second_user
        create_conv(client, auth_headers, "Conv Alice")
        resp = client.get("/conversations", headers=bob_headers)
        assert all(c["title"] != "Conv Alice" for c in resp.json())


# ─────────────────────────────────────────────────────────────────────────────
# Créer une conversation
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateConversation:
    def test_create_success(self, client, auth_headers, inject_rag):
        inject_rag.new_session.return_value = "sess-abc-123"
        resp = client.post("/conversations", json={"title": "Ma conv"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Ma conv"
        assert "id" in data
        assert "session_id" in data
        assert data["message_count"] == 0

    def test_create_default_title(self, client, auth_headers):
        resp = client.post("/conversations", json={}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Nouvelle conversation"

    def test_create_requires_auth(self, client):
        resp = client.post("/conversations", json={"title": "Test"})
        assert resp.status_code == 401

    def test_create_increments_list(self, client, auth_headers):
        create_conv(client, auth_headers)
        create_conv(client, auth_headers)
        resp = client.get("/conversations", headers=auth_headers)
        assert len(resp.json()) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Lire une conversation
# ─────────────────────────────────────────────────────────────────────────────

class TestGetConversation:
    def test_get_own_conversation(self, client, auth_headers):
        conv = create_conv(client, auth_headers, "Test")
        resp = client.get(f"/conversations/{conv['id']}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == conv["id"]
        assert data["title"] == "Test"
        assert isinstance(data["messages"], list)

    def test_get_unknown_conversation_404(self, client, auth_headers):
        resp = client.get("/conversations/inexistant", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_other_users_conversation_404(self, client, auth_headers, second_user):
        _, bob_headers = second_user
        conv = create_conv(client, auth_headers, "Alice secrète")
        # Bob ne doit pas y accéder
        resp = client.get(f"/conversations/{conv['id']}", headers=bob_headers)
        assert resp.status_code == 404

    def test_get_conversation_requires_auth(self, client, auth_headers):
        conv = create_conv(client, auth_headers)
        resp = client.get(f"/conversations/{conv['id']}")
        assert resp.status_code == 401

    def test_get_conversation_with_messages(self, client, auth_headers):
        conv = create_conv(client, auth_headers)
        # Ajouter un message
        client.post(
            f"/conversations/{conv['id']}/messages",
            json={"role": "user", "content": "Bonjour !"},
            headers=auth_headers,
        )
        resp = client.get(f"/conversations/{conv['id']}", headers=auth_headers)
        msgs = resp.json()["messages"]
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Bonjour !"


# ─────────────────────────────────────────────────────────────────────────────
# Supprimer une conversation
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteConversation:
    def test_delete_own_conversation(self, client, auth_headers):
        conv = create_conv(client, auth_headers)
        resp = client.delete(f"/conversations/{conv['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # Vérifie que la conv est bien supprimée
        resp2 = client.get(f"/conversations/{conv['id']}", headers=auth_headers)
        assert resp2.status_code == 404

    def test_delete_removes_from_list(self, client, auth_headers):
        conv = create_conv(client, auth_headers)
        client.delete(f"/conversations/{conv['id']}", headers=auth_headers)
        resp = client.get("/conversations", headers=auth_headers)
        assert all(c["id"] != conv["id"] for c in resp.json())

    def test_delete_other_users_conversation_404(self, client, auth_headers, second_user):
        _, bob_headers = second_user
        conv = create_conv(client, auth_headers)
        resp = client.delete(f"/conversations/{conv['id']}", headers=bob_headers)
        assert resp.status_code == 404

    def test_delete_unknown_conversation_404(self, client, auth_headers):
        resp = client.delete("/conversations/inexistant", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_requires_auth(self, client, auth_headers):
        conv = create_conv(client, auth_headers)
        resp = client.delete(f"/conversations/{conv['id']}")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Renommer une conversation
# ─────────────────────────────────────────────────────────────────────────────

class TestRenameConversation:
    def test_rename_success(self, client, auth_headers):
        conv = create_conv(client, auth_headers, "Ancien titre")
        resp = client.patch(
            f"/conversations/{conv['id']}",
            json={"title": "Nouveau titre"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # Vérifie dans la liste
        list_resp = client.get("/conversations", headers=auth_headers)
        titles = [c["title"] for c in list_resp.json()]
        assert "Nouveau titre" in titles

    def test_rename_empty_title_fails(self, client, auth_headers):
        conv = create_conv(client, auth_headers)
        resp = client.patch(
            f"/conversations/{conv['id']}",
            json={"title": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_rename_other_users_conversation_404(self, client, auth_headers, second_user):
        _, bob_headers = second_user
        conv = create_conv(client, auth_headers)
        resp = client.patch(
            f"/conversations/{conv['id']}",
            json={"title": "Hack"},
            headers=bob_headers,
        )
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Ajouter des messages
# ─────────────────────────────────────────────────────────────────────────────

class TestAddMessage:
    def test_add_user_message(self, client, auth_headers):
        conv = create_conv(client, auth_headers)
        resp = client.post(
            f"/conversations/{conv['id']}/messages",
            json={"role": "user", "content": "Quelle est la TVA ?"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        msg = resp.json()
        assert msg["role"] == "user"
        assert msg["content"] == "Quelle est la TVA ?"
        assert "id" in msg
        assert "created_at" in msg

    def test_add_assistant_message(self, client, auth_headers):
        conv = create_conv(client, auth_headers)
        resp = client.post(
            f"/conversations/{conv['id']}/messages",
            json={"role": "assistant", "content": "La TVA est à 20%.", "source": "rag"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "assistant"
        assert resp.json()["source"] == "rag"

    def test_add_message_auto_title(self, client, auth_headers):
        """Premier message user → le titre de la conv est mis à jour."""
        conv = create_conv(client, auth_headers, "Nouvelle conversation")
        client.post(
            f"/conversations/{conv['id']}/messages",
            json={"role": "user", "content": "Comment facturer une étude ?"},
            headers=auth_headers,
        )
        list_resp = client.get("/conversations", headers=auth_headers)
        conv_data = next(c for c in list_resp.json() if c["id"] == conv["id"])
        assert conv_data["title"] == "Comment facturer une étude ?"

    def test_add_message_invalid_role(self, client, auth_headers):
        conv = create_conv(client, auth_headers)
        resp = client.post(
            f"/conversations/{conv['id']}/messages",
            json={"role": "system", "content": "Injection"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_add_message_to_other_users_conv_404(self, client, auth_headers, second_user):
        _, bob_headers = second_user
        conv = create_conv(client, auth_headers)
        resp = client.post(
            f"/conversations/{conv['id']}/messages",
            json={"role": "user", "content": "Hack"},
            headers=bob_headers,
        )
        assert resp.status_code == 404

    def test_add_message_count_increments(self, client, auth_headers):
        conv = create_conv(client, auth_headers)
        for i in range(3):
            client.post(
                f"/conversations/{conv['id']}/messages",
                json={"role": "user", "content": f"Message {i}"},
                headers=auth_headers,
            )
        list_resp = client.get("/conversations", headers=auth_headers)
        conv_data = next(c for c in list_resp.json() if c["id"] == conv["id"])
        assert conv_data["message_count"] == 3
