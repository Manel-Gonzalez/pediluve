import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from routers.me import get_current_user
from services.auth import AuthenticatedUser

client = TestClient(app)

USER = AuthenticatedUser(id="user-1", email="a@example.com", access_token="tok")


@pytest.fixture
def authed():
    app.dependency_overrides[get_current_user] = lambda: USER
    yield USER
    app.dependency_overrides.clear()


def _session_row(**overrides):
    row = {
        "id": str(uuid.uuid4()),
        "user_id": USER.id,
        "title": "Standup",
        "source_language": None,
        "target_language": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "role": "owner",
        "share_token": str(uuid.uuid4()),
        "guest_language": None,
    }
    row.update(overrides)
    return row


# ── auth gate ─────────────────────────────────────────────────────────────


def test_list_sessions_without_authorization_is_401():
    response = client.get("/api/sessions")
    assert response.status_code == 401


def test_create_session_without_authorization_is_401():
    response = client.post("/api/sessions", json={"title": "Standup"})
    assert response.status_code == 401


# ── POST /api/sessions ───────────────────────────────────────────────────


def test_create_session_returns_the_created_row(monkeypatch, authed):
    row = _session_row(title="Standup")

    async def fake_create_session(user, title):
        assert user is authed
        assert title == "Standup"
        return row

    monkeypatch.setattr("routers.sessions.supabase.create_session", fake_create_session)

    response = client.post("/api/sessions", json={"title": "Standup"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == row["id"]
    assert body["title"] == "Standup"
    assert body["message_count"] == 0


@pytest.mark.parametrize("title", ["", "   ", "x" * 121])
def test_create_session_rejects_an_invalid_title(authed, title):
    response = client.post("/api/sessions", json={"title": title})
    assert response.status_code == 422


# ── GET /api/sessions ────────────────────────────────────────────────────


def test_list_sessions_returns_the_expected_shape(monkeypatch, authed):
    row = _session_row(message_count=2)

    async def fake_list_sessions(user, limit, offset):
        assert user is authed
        return [row], True

    monkeypatch.setattr("routers.sessions.supabase.list_sessions", fake_list_sessions)

    response = client.get("/api/sessions")

    assert response.status_code == 200
    body = response.json()
    assert body["has_more"] is True
    assert body["items"][0]["id"] == row["id"]
    assert body["items"][0]["message_count"] == 2


def test_list_sessions_passes_limit_and_offset_through(monkeypatch, authed):
    captured = {}

    async def fake_list_sessions(user, limit, offset):
        captured["limit"] = limit
        captured["offset"] = offset
        return [], False

    monkeypatch.setattr("routers.sessions.supabase.list_sessions", fake_list_sessions)

    response = client.get("/api/sessions", params={"limit": 5, "offset": 10})

    assert response.status_code == 200
    assert captured == {"limit": 5, "offset": 10}


def test_list_sessions_clamps_limit_to_100(monkeypatch, authed):
    captured = {}

    async def fake_list_sessions(user, limit, offset):
        captured["limit"] = limit
        return [], False

    monkeypatch.setattr("routers.sessions.supabase.list_sessions", fake_list_sessions)

    response = client.get("/api/sessions", params={"limit": 500})

    assert response.status_code == 200
    assert captured["limit"] == 100


# ── GET /api/sessions/{id} ───────────────────────────────────────────────


def test_get_session_returns_the_expected_shape(monkeypatch, authed):
    row = _session_row()
    row["messages"] = [
        {
            "id": "msg-1",
            "sequence": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        }
    ]

    async def fake_get_session_with_messages(user, session_id):
        assert session_id == row["id"]
        return row

    monkeypatch.setattr(
        "routers.sessions.supabase.get_session_with_messages", fake_get_session_with_messages
    )

    response = client.get(f"/api/sessions/{row['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == row["id"]
    assert body["message_count"] == 1
    assert body["messages"][0]["original_text"] == "hello"


def test_get_session_with_an_unknown_id_is_404(monkeypatch, authed):
    async def fake_get_session_with_messages(user, session_id):
        return None

    monkeypatch.setattr(
        "routers.sessions.supabase.get_session_with_messages", fake_get_session_with_messages
    )

    response = client.get(f"/api/sessions/{uuid.uuid4()}")

    assert response.status_code == 404


def test_get_session_with_a_non_uuid_id_is_404(authed):
    response = client.get("/api/sessions/not-a-uuid")
    assert response.status_code == 404


# ── PATCH /api/sessions/{id} ─────────────────────────────────────────────


def test_rename_session_returns_the_updated_row(monkeypatch, authed):
    row = _session_row(title="New title")

    async def fake_rename_session(user, session_id, title):
        assert session_id == row["id"]
        assert title == "New title"
        return row

    async def fake_get_session_with_messages(user, session_id):
        return {**row, "messages": []}

    monkeypatch.setattr("routers.sessions.supabase.rename_session", fake_rename_session)
    monkeypatch.setattr(
        "routers.sessions.supabase.get_session_with_messages", fake_get_session_with_messages
    )

    response = client.patch(f"/api/sessions/{row['id']}", json={"title": "New title"})

    assert response.status_code == 200
    assert response.json()["title"] == "New title"


def test_rename_session_rejects_a_blank_title(authed):
    response = client.patch(f"/api/sessions/{uuid.uuid4()}", json={"title": ""})
    assert response.status_code == 422


def test_rename_session_with_an_unknown_id_is_404(monkeypatch, authed):
    async def fake_rename_session(user, session_id, title):
        return None

    monkeypatch.setattr("routers.sessions.supabase.rename_session", fake_rename_session)

    response = client.patch(f"/api/sessions/{uuid.uuid4()}", json={"title": "New title"})

    assert response.status_code == 404


def test_rename_session_with_a_non_uuid_id_is_404(authed):
    response = client.patch("/api/sessions/not-a-uuid", json={"title": "New title"})
    assert response.status_code == 404


# ── DELETE /api/sessions/{id} ────────────────────────────────────────────


def test_delete_session_returns_204(monkeypatch, authed):
    async def fake_delete_session(user, session_id):
        return True

    monkeypatch.setattr("routers.sessions.supabase.delete_session", fake_delete_session)

    response = client.delete(f"/api/sessions/{uuid.uuid4()}")

    assert response.status_code == 204


def test_delete_session_with_an_unknown_id_is_404(monkeypatch, authed):
    async def fake_delete_session(user, session_id):
        return False

    monkeypatch.setattr("routers.sessions.supabase.delete_session", fake_delete_session)

    response = client.delete(f"/api/sessions/{uuid.uuid4()}")

    assert response.status_code == 404


def test_delete_session_with_a_non_uuid_id_is_404(authed):
    response = client.delete("/api/sessions/not-a-uuid")
    assert response.status_code == 404


def test_delete_session_also_deletes_its_cached_audio(monkeypatch, authed):
    calls = []

    async def fake_delete_session_audio(user, owner_id, session_id):
        calls.append((owner_id, session_id))

    async def fake_delete_session(user, session_id):
        return True

    monkeypatch.setattr("routers.sessions.storage.delete_session_audio", fake_delete_session_audio)
    monkeypatch.setattr("routers.sessions.supabase.delete_session", fake_delete_session)

    session_id = str(uuid.uuid4())
    response = client.delete(f"/api/sessions/{session_id}")

    assert response.status_code == 204
    assert calls == [(USER.id, session_id)]


def test_delete_session_succeeds_even_if_audio_cleanup_fails(monkeypatch, authed):
    async def failing_delete_session_audio(user, owner_id, session_id):
        raise RuntimeError("Storage is down")

    async def fake_delete_session(user, session_id):
        return True

    monkeypatch.setattr("routers.sessions.storage.delete_session_audio", failing_delete_session_audio)
    monkeypatch.setattr("routers.sessions.supabase.delete_session", fake_delete_session)

    response = client.delete(f"/api/sessions/{uuid.uuid4()}")

    assert response.status_code == 204


# ── POST /api/sessions/{id}/translate ────────────────────────────────────


def test_translate_session_returns_translations_in_order(monkeypatch, authed):
    row = _session_row()
    row["messages"] = [
        {
            "id": "msg-1",
            "sequence": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        },
        {
            "id": "msg-2",
            "sequence": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "original_text": "world",
            "translated_text": None,
            "target_language": None,
        },
    ]

    async def fake_get_session_with_messages(user, session_id):
        return row

    async def fake_translate_many(texts, target_language):
        assert texts == ["hello", "world"]
        assert target_language == "es"
        return ["hola", "mundo"]

    monkeypatch.setattr(
        "routers.sessions.supabase.get_session_with_messages", fake_get_session_with_messages
    )
    monkeypatch.setattr("routers.sessions.deepl.translate_many", fake_translate_many)

    response = client.post(f"/api/sessions/{row['id']}/translate", json={"target_language": "es"})

    assert response.status_code == 200
    body = response.json()
    assert body["target_language"] == "es"
    assert body["translations"] == [
        {"message_id": "msg-1", "translated_text": "hola"},
        {"message_id": "msg-2", "translated_text": "mundo"},
    ]


def test_translate_session_with_an_unsupported_language_is_400(monkeypatch, authed):
    async def unexpected_call(*args, **kwargs):
        raise AssertionError("should not be called for an unsupported language")

    monkeypatch.setattr("routers.sessions.supabase.get_session_with_messages", unexpected_call)
    monkeypatch.setattr("routers.sessions.deepl.translate_many", unexpected_call)

    response = client.post(f"/api/sessions/{uuid.uuid4()}/translate", json={"target_language": "xx"})

    assert response.status_code == 400


def test_translate_session_with_an_unknown_id_is_404_and_deepl_is_not_called(monkeypatch, authed):
    async def fake_get_session_with_messages(user, session_id):
        return None

    async def unexpected_translate_many(*args, **kwargs):
        raise AssertionError("deepl.translate_many should not be called for an unknown session")

    monkeypatch.setattr(
        "routers.sessions.supabase.get_session_with_messages", fake_get_session_with_messages
    )
    monkeypatch.setattr("routers.sessions.deepl.translate_many", unexpected_translate_many)

    response = client.post(f"/api/sessions/{uuid.uuid4()}/translate", json={"target_language": "es"})

    assert response.status_code == 404


def test_translate_session_with_a_non_uuid_id_is_404(authed):
    response = client.post("/api/sessions/not-a-uuid/translate", json={"target_language": "es"})
    assert response.status_code == 404


def test_translate_session_maps_a_failed_translation_to_null(monkeypatch, authed):
    row = _session_row()
    row["messages"] = [
        {
            "id": "msg-1",
            "sequence": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        }
    ]

    async def fake_get_session_with_messages(user, session_id):
        return row

    async def fake_translate_many(texts, target_language):
        return [None]

    monkeypatch.setattr(
        "routers.sessions.supabase.get_session_with_messages", fake_get_session_with_messages
    )
    monkeypatch.setattr("routers.sessions.deepl.translate_many", fake_translate_many)

    response = client.post(f"/api/sessions/{row['id']}/translate", json={"target_language": "es"})

    assert response.status_code == 200
    assert response.json()["translations"] == [{"message_id": "msg-1", "translated_text": None}]


def test_translate_session_with_no_messages_returns_an_empty_list_and_does_not_call_deepl(
    monkeypatch, authed
):
    row = _session_row()
    row["messages"] = []

    async def fake_get_session_with_messages(user, session_id):
        return row

    async def unexpected_translate_many(*args, **kwargs):
        raise AssertionError("deepl.translate_many should not be called for an empty session")

    monkeypatch.setattr(
        "routers.sessions.supabase.get_session_with_messages", fake_get_session_with_messages
    )
    monkeypatch.setattr("routers.sessions.deepl.translate_many", unexpected_translate_many)

    response = client.post(f"/api/sessions/{row['id']}/translate", json={"target_language": "es"})

    assert response.status_code == 200
    assert response.json()["translations"] == []


# ── POST /api/shared/guest ───────────────────────────────────────────────


def test_add_guest_returns_the_newly_accessible_session(monkeypatch, authed):
    row = _session_row(
        role="guest", guest_language="fr", share_token="share-token-123", message_count=0
    )
    calls = []

    async def fake_add_session_guest(user, share_token, target_language):
        calls.append((share_token, target_language))

    async def fake_get_session_by_share_token(user, share_token):
        assert share_token == "share-token-123"
        return row

    monkeypatch.setattr("routers.sessions.supabase.add_session_guest", fake_add_session_guest)
    monkeypatch.setattr(
        "routers.sessions.supabase.get_session_by_share_token", fake_get_session_by_share_token
    )

    response = client.post(
        "/api/shared/guest", json={"share_token": "share-token-123", "target_language": "fr"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == row["id"]
    assert body["role"] == "guest"
    assert body["guest_language"] == "fr"
    assert calls == [("share-token-123", "fr")]


def test_add_guest_with_an_unknown_token_is_404(monkeypatch, authed):
    async def failing_add_session_guest(user, share_token, target_language):
        raise Exception("Session not found")

    monkeypatch.setattr("routers.sessions.supabase.add_session_guest", failing_add_session_guest)

    response = client.post("/api/shared/guest", json={"share_token": "does-not-exist"})

    assert response.status_code == 404


def test_add_guest_without_authorization_is_401():
    response = client.post("/api/shared/guest", json={"share_token": "x"})
    assert response.status_code == 401


# ── DELETE /api/sessions/{id}/guest ──────────────────────────────────────


def test_remove_guest_returns_204(monkeypatch, authed):
    async def fake_remove_session_guest(user, session_id):
        return True

    monkeypatch.setattr("routers.sessions.supabase.remove_session_guest", fake_remove_session_guest)

    response = client.delete(f"/api/sessions/{uuid.uuid4()}/guest")

    assert response.status_code == 204


def test_remove_guest_with_no_matching_membership_is_404(monkeypatch, authed):
    async def fake_remove_session_guest(user, session_id):
        return False

    monkeypatch.setattr("routers.sessions.supabase.remove_session_guest", fake_remove_session_guest)

    response = client.delete(f"/api/sessions/{uuid.uuid4()}/guest")

    assert response.status_code == 404


def test_remove_guest_with_a_non_uuid_id_is_404(authed):
    response = client.delete("/api/sessions/not-a-uuid/guest")
    assert response.status_code == 404
