"""
Tests — Authentification (unités + intégration)
"""

import pytest
from datetime import datetime, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# Tests unitaires — fonctions auth.py
# ─────────────────────────────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_produces_bcrypt_string(self):
        from auth import hash_password
        hashed = hash_password("motdepasse")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_hash_is_different_each_call(self):
        from auth import hash_password
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # sel aléatoire à chaque fois

    def test_verify_correct_password(self):
        from auth import hash_password, verify_password
        hashed = hash_password("bonjour123")
        assert verify_password("bonjour123", hashed) is True

    def test_verify_wrong_password(self):
        from auth import hash_password, verify_password
        hashed = hash_password("bonjour123")
        assert verify_password("mauvais", hashed) is False

    def test_verify_empty_password_fails(self):
        from auth import hash_password, verify_password
        hashed = hash_password("secret")
        assert verify_password("", hashed) is False


class TestJWT:
    def test_create_token_returns_string(self):
        from auth import create_token
        token = create_token("user-123", "test@je.fr")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_valid_token(self):
        from auth import create_token, decode_token
        token = create_token("user-abc", "test@je.fr")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-abc"
        assert payload["email"] == "test@je.fr"

    def test_decode_invalid_token_returns_none(self):
        from auth import decode_token
        assert decode_token("not.a.valid.token") is None

    def test_decode_tampered_token_returns_none(self):
        from auth import create_token, decode_token
        token = create_token("user-xyz", "test@je.fr")
        # Altère la signature
        tampered = token[:-5] + "XXXXX"
        assert decode_token(tampered) is None

    def test_decode_expired_token_returns_none(self):
        import jwt, os
        from datetime import datetime, timedelta
        secret = os.getenv("NEXTAUTH_SECRET", "comply-secret-change-me-in-production")
        expired_payload = {
            "sub": "user-expired",
            "email": "expired@je.fr",
            "exp": datetime.utcnow() - timedelta(seconds=1),
        }
        token = jwt.encode(expired_payload, secret, algorithm="HS256")
        from auth import decode_token
        assert decode_token(token) is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests d'intégration — endpoints /auth/
# ─────────────────────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_success(self, client):
        resp = client.post("/auth/register", json={
            "email": "nouveau@je.fr",
            "name": "Nouvel Utilisateur",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "nouveau@je.fr"
        assert data["name"] == "Nouvel Utilisateur"
        assert "token" in data
        assert "id" in data

    def test_register_email_normalised_to_lowercase(self, client):
        resp = client.post("/auth/register", json={
            "email": "MAJUSCULES@JE.FR",
            "name": "Test",
            "password": "password123",
        })
        assert resp.status_code == 200
        assert resp.json()["email"] == "majuscules@je.fr"

    def test_register_duplicate_email_fails(self, client):
        payload = {"email": "dupe@je.fr", "name": "A", "password": "pass123"}
        client.post("/auth/register", json=payload)
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 400
        assert "déjà utilisée" in resp.json()["detail"]

    def test_register_password_too_short_fails(self, client):
        resp = client.post("/auth/register", json={
            "email": "short@je.fr",
            "name": "Test",
            "password": "abc",  # < 6 chars
        })
        assert resp.status_code == 422

    def test_register_missing_email_fails(self, client):
        resp = client.post("/auth/register", json={
            "name": "Test",
            "password": "password123",
        })
        assert resp.status_code == 422

    def test_register_missing_name_fails(self, client):
        resp = client.post("/auth/register", json={
            "email": "noname@je.fr",
            "password": "password123",
        })
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client, registered_user):
        resp = client.post("/auth/login", json={
            "email": "alice@je.fr",
            "password": "securepass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "alice@je.fr"
        assert "token" in data

    def test_login_wrong_password(self, client, registered_user):
        resp = client.post("/auth/login", json={
            "email": "alice@je.fr",
            "password": "mauvaismdp",
        })
        assert resp.status_code == 401
        assert "incorrect" in resp.json()["detail"]

    def test_login_unknown_email(self, client):
        resp = client.post("/auth/login", json={
            "email": "inconnu@je.fr",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_login_case_insensitive_email(self, client, registered_user):
        resp = client.post("/auth/login", json={
            "email": "ALICE@JE.FR",
            "password": "securepass123",
        })
        assert resp.status_code == 200


class TestMe:
    def test_me_authenticated(self, client, registered_user, auth_headers):
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "alice@je.fr"
        assert data["name"] == "Alice Dupont"
        assert "id" in data
        assert "created_at" in data

    def test_me_unauthenticated(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401

    def test_token_is_valid_jwt(self, client, registered_user):
        from auth import decode_token
        token = registered_user["token"]
        payload = decode_token(token)
        assert payload is not None
        assert payload["email"] == "alice@je.fr"
