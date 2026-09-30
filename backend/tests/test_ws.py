import asyncio
import time
import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDisconnect

from main import app
import routers.ws as ws_module
from services import live_rooms
from services.auth import AuthenticatedUser, AuthError, AuthServiceUnavailable

client = TestClient(app)

DEFAULT_USER = AuthenticatedUser(id="user-1", email="user1@example.com", access_token="valid-token")
OTHER_USER = AuthenticatedUser(id="user-2", email="user2@example.com", access_token="other-token")
REFRESHED_USER = AuthenticatedUser(id="user-1", email="user1@example.com", access_token="refreshed-token")

_KNOWN_TOKENS = {
    DEFAULT_USER.access_token: DEFAULT_USER,
    OTHER_USER.access_token: OTHER_USER,
    REFRESHED_USER.access_token: REFRESHED_USER,
}


@pytest.fixture(autouse=True)
def fake_verify_access_token(monkeypatch):
    async def fake_verify(token):
        user = _KNOWN_TOKENS.get(token)
        if user is None:
            raise AuthError("invalid token")
        return user

    monkeypatch.setattr("routers.ws.verify_access_token", fake_verify)


@contextmanager
def _authenticated_connection(user: AuthenticatedUser = DEFAULT_USER):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "authenticate", "access_token": user.access_token})
        assert ws.receive_json() == {"type": "authenticated", "user_id": user.id}
        yield ws


@pytest.fixture
def authenticated_ws():
    return _authenticated_connection


class _FakeSupabase:
    # A fake covering only the session/message operations ws.py still calls
    # directly (create_session is no longer one of them - sessions are
    # created via the REST API, see KAN-36). seed_session lets a test set up
    # a session as if it already existed before this connection joined it.
    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.messages: list[dict] = []

    def seed_session(
        self,
        *,
        user_id: str = DEFAULT_USER.id,
        title: str | None = "Test session",
        source_language: str | None = None,
        target_language: str | None = None,
        messages: list | None = None,
        # Simulates a future guest-visible RLS row (KAN-59): the row is
        # returned by get_session_with_messages even to a non-owner, so
        # tests can exercise ws.py's own explicit ownership guard (KAN-54)
        # independent of RLS.
        guest_visible: bool = False,
        share_token: str | None = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "id": session_id,
            "user_id": user_id,
            "title": title,
            "source_language": source_language,
            "target_language": target_language,
            "ended_at": None,
            "share_token": share_token or str(uuid.uuid4()),
            "guest_visible": guest_visible,
        }
        for index, message in enumerate(messages or []):
            if isinstance(message, str):
                message = {"original_text": message}
            self.messages.append(
                {
                    "session_id": session_id,
                    "sequence": message.get("sequence", index),
                    "original_text": message["original_text"],
                    "translated_text": message.get("translated_text"),
                    "target_language": message.get("target_language"),
                }
            )
        return session_id

    async def get_session_with_messages(self, user, session_id):
        session = self.sessions.get(session_id)
        if session is None:
            return None
        if session["user_id"] != user.id and not session["guest_visible"]:
            return None
        messages = sorted(
            (m for m in self.messages if m["session_id"] == session_id),
            key=lambda m: m["sequence"],
        )
        return {**session, "messages": messages}

    async def save_message(
        self, user, session_id, sequence, original_text, translated_text=None, target_language=None
    ):
        self.messages.append(
            {
                "user_id": user.id,
                "access_token": user.access_token,
                "session_id": session_id,
                "sequence": sequence,
                "original_text": original_text,
                "translated_text": translated_text,
                "target_language": target_language,
            }
        )

    async def update_session_target_language(self, user, session_id, target_language):
        self.sessions[session_id]["target_language"] = target_language

    async def update_session_source_language(self, user, session_id, source_language):
        self.sessions[session_id]["source_language"] = source_language

    async def end_session(self, user, session_id):
        self.sessions[session_id]["ended_at"] = "now"


@pytest.fixture(autouse=True)
def fake_supabase(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr("routers.ws.supabase.get_session_with_messages", fake.get_session_with_messages)
    monkeypatch.setattr("routers.ws.supabase.save_message", fake.save_message)
    monkeypatch.setattr(
        "routers.ws.supabase.update_session_target_language", fake.update_session_target_language
    )
    monkeypatch.setattr(
        "routers.ws.supabase.update_session_source_language", fake.update_session_source_language
    )
    monkeypatch.setattr("routers.ws.supabase.end_session", fake.end_session)
    return fake


@pytest.fixture
def joined_ws(fake_supabase):
    @contextmanager
    def _make(user: AuthenticatedUser = DEFAULT_USER, **session_kwargs):
        session_id = fake_supabase.seed_session(user_id=user.id, **session_kwargs)
        with _authenticated_connection(user) as ws:
            ws.send_json({"type": "join_session", "session_id": session_id})
            joined = ws.receive_json()
            assert joined["type"] == "session_joined"
            yield ws, session_id

    return _make


def make_fake_session_class(canned_events):
    class FakeRealtimeSession:
        instances: list["FakeRealtimeSession"] = []

        def __init__(self) -> None:
            self.closed = False
            self.audio_chunks: list[bytes] = []
            self.audio_format: str | None = None
            FakeRealtimeSession.instances.append(self)

        async def connect(self, audio_format: str = "pcm_16000") -> None:
            self.audio_format = audio_format

        async def send_audio(self, pcm_bytes: bytes) -> None:
            self.audio_chunks.append(pcm_bytes)

        async def events(self):
            for event in canned_events:
                yield event

        async def close(self) -> None:
            self.closed = True

    return FakeRealtimeSession


# ── Authentication gate ──────────────────────────────────────────────────


def test_authenticate_succeeds_and_replies_authenticated():
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "authenticate", "access_token": DEFAULT_USER.access_token})
        assert ws.receive_json() == {"type": "authenticated", "user_id": DEFAULT_USER.id}


def test_authenticate_with_an_invalid_token_is_rejected_and_closed():
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "authenticate", "access_token": "bad-token"})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_authenticate_with_an_invalid_payload_is_rejected_and_closed():
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "authenticate"})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_start_transcription_before_authenticating_is_rejected_and_closed(monkeypatch):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start_transcription"})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    assert fake_cls.instances == []


def test_join_session_before_authenticating_is_rejected_and_closed():
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join_session", "session_id": str(uuid.uuid4())})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == ws_module.AUTH_REQUIRED_CLOSE_CODE


def test_audio_bytes_before_authenticating_closes_the_connection():
    with client.websocket_connect("/ws") as ws:
        ws.send_bytes(b"\x00\x01")
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_message_before_authenticating_is_rejected_and_closed():
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "message", "text": "hi"})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_set_target_language_before_authenticating_is_rejected_and_closed():
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_reauthenticating_as_the_same_user_replaces_the_token_used_for_later_saves(
    monkeypatch, fake_supabase
):
    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    session_id = fake_supabase.seed_session()

    with _authenticated_connection() as ws:
        # Simulates a refreshed Supabase access token arriving mid-connection.
        ws.send_json({"type": "authenticate", "access_token": REFRESHED_USER.access_token})
        assert ws.receive_json() == {"type": "authenticated", "user_id": REFRESHED_USER.id}

        ws.send_json({"type": "join_session", "session_id": session_id})
        ws.receive_json()  # session_joined

        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    saved = next(m for m in fake_supabase.messages if m["session_id"] == session_id)
    assert saved["access_token"] == REFRESHED_USER.access_token


def test_reauthenticating_as_a_different_user_is_rejected_and_closed():
    with _authenticated_connection(DEFAULT_USER) as ws:
        ws.send_json({"type": "authenticate", "access_token": OTHER_USER.access_token})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_invalid_json_before_authenticating_is_rejected_and_closed():
    with client.websocket_connect("/ws") as ws:
        ws.send_text("not json")
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_authenticate_when_the_service_is_unavailable_uses_a_distinct_close_code(monkeypatch):
    async def unavailable_verify(token):
        raise AuthServiceUnavailable("down")

    monkeypatch.setattr("routers.ws.verify_access_token", unavailable_verify)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "authenticate", "access_token": "whatever"})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == ws_module.AUTH_SERVICE_UNAVAILABLE_CLOSE_CODE
        assert exc_info.value.code != ws_module.AUTH_REQUIRED_CLOSE_CODE


def test_disconnecting_mid_session_still_persists_in_flight_committed_transcripts(
    monkeypatch, authenticated_ws, fake_supabase
):
    async def slow_translate(text, target_language):
        await asyncio.sleep(0.05)
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", slow_translate)

    canned = [
        {"message_type": "committed_transcript", "text": "hello"},
        {"message_type": "committed_transcript", "text": "world"},
    ]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    session_id = fake_supabase.seed_session(target_language="es")

    with authenticated_ws() as ws:
        ws.send_json({"type": "join_session", "session_id": session_id})
        ws.receive_json()  # session_joined
        ws.send_json({"type": "start_transcription"})
        # Disconnect immediately - before either committed transcript has been
        # relayed or saved, both still in flight behind the slow translate.

    saved = [m for m in fake_supabase.messages if m["session_id"] == session_id]
    assert len(saved) == 2
    assert [m["original_text"] for m in saved] == ["hello", "world"]


# ── join_session ──────────────────────────────────────────────────────────


def test_join_session_returns_stored_transcripts(fake_supabase, authenticated_ws):
    session_id = fake_supabase.seed_session(
        title="Standup",
        source_language="en",
        target_language="es",
        messages=[
            {"original_text": "hello", "translated_text": "hola", "target_language": "es"},
            {"original_text": "world", "translated_text": "mundo", "target_language": "es"},
        ],
    )

    with authenticated_ws() as ws:
        ws.send_json({"type": "join_session", "session_id": session_id})
        assert ws.receive_json() == {
            "type": "session_joined",
            "session_id": session_id,
            "title": "Standup",
            "source_language": "en",
            "target_language": "es",
            "transcripts": [
                {
                    "type": "transcript",
                    "original_text": "hello",
                    "translated_text": "hola",
                    "target_language": "es",
                },
                {
                    "type": "transcript",
                    "original_text": "world",
                    "translated_text": "mundo",
                    "target_language": "es",
                },
            ],
            "share_token": fake_supabase.sessions[session_id]["share_token"],
        }


def test_join_session_with_an_unknown_id_is_rejected_and_closed(authenticated_ws):
    with authenticated_ws() as ws:
        ws.send_json({"type": "join_session", "session_id": str(uuid.uuid4())})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == ws_module.SESSION_NOT_FOUND_CLOSE_CODE


def test_join_session_owned_by_another_user_is_rejected_and_closed(fake_supabase, authenticated_ws):
    session_id = fake_supabase.seed_session(user_id=OTHER_USER.id)

    with authenticated_ws() as ws:
        ws.send_json({"type": "join_session", "session_id": session_id})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == ws_module.SESSION_NOT_FOUND_CLOSE_CODE


def test_join_session_visible_but_not_owned_is_rejected_and_closed(fake_supabase, authenticated_ws):
    # Simulates a future guest-visible RLS row (KAN-59): the row itself is
    # returned by get_session_with_messages (guest_visible=True), so this
    # guard must be ws.py's own explicit ownership check, not just RLS -
    # a guest must never be able to open the owner's live/recording view.
    session_id = fake_supabase.seed_session(user_id=OTHER_USER.id, guest_visible=True)

    with authenticated_ws() as ws:
        ws.send_json({"type": "join_session", "session_id": session_id})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == ws_module.SESSION_NOT_FOUND_CLOSE_CODE


def test_join_session_with_a_non_uuid_id_is_rejected_and_closed(authenticated_ws):
    with authenticated_ws() as ws:
        ws.send_json({"type": "join_session", "session_id": "not-a-uuid"})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == ws_module.SESSION_NOT_FOUND_CLOSE_CODE


def test_joining_a_second_session_is_rejected_without_closing(joined_ws, fake_supabase):
    with joined_ws() as (ws, _first_session_id):
        second_session_id = fake_supabase.seed_session()
        ws.send_json({"type": "join_session", "session_id": second_session_id})
        error = ws.receive_json()
        assert error["type"] == "error"

        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}


def test_joining_a_session_with_stored_messages_continues_the_sequence(
    monkeypatch, fake_supabase, authenticated_ws
):
    session_id = fake_supabase.seed_session(messages=["one", "two", "three"])

    canned = [{"message_type": "committed_transcript", "text": "four"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "join_session", "session_id": session_id})
        ws.receive_json()  # session_joined
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()  # "four"
        ws.send_json({"type": "stop_transcription"})

    saved = next(
        m
        for m in fake_supabase.messages
        if m["session_id"] == session_id and m["original_text"] == "four"
    )
    assert saved["sequence"] == 3


# ── Everything below requires authentication first ──────────────────────


def test_echo_roundtrip(authenticated_ws):
    with authenticated_ws() as ws:
        ws.send_json({"type": "message", "text": "hola"})
        assert ws.receive_json() == {"type": "echo", "text": "hola"}


def test_invalid_json_returns_error_and_keeps_socket_open(authenticated_ws):
    with authenticated_ws() as ws:
        ws.send_text("not json")
        error = ws.receive_json()
        assert error["type"] == "error"

        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}


def test_unknown_message_type_returns_error(authenticated_ws):
    with authenticated_ws() as ws:
        ws.send_json({"type": "not_a_real_type"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "not_a_real_type" in error["message"]


def test_start_transcription_before_joining_is_rejected_without_closing(monkeypatch, authenticated_ws):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        error = ws.receive_json()
        assert error["type"] == "error"

        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}

    assert fake_cls.instances == []


def test_set_target_language_before_joining_is_rejected_without_closing(authenticated_ws):
    with authenticated_ws() as ws:
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        error = ws.receive_json()
        assert error["type"] == "error"

        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}


def test_start_transcription_relays_partial_and_committed_events(monkeypatch, joined_ws):
    canned = [
        {"message_type": "session_started", "session_id": "abc"},
        {"message_type": "partial_transcript", "text": "hel"},
        {"message_type": "committed_transcript", "text": "hello"},
    ]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription", "audio_format": "pcm_16000"})
        assert ws.receive_json() == {"type": "partial_transcript", "text": "hel"}
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        }

    assert fake_cls.instances[0].audio_format == "pcm_16000"


def test_empty_committed_transcripts_are_not_processed(monkeypatch, joined_ws, fake_supabase):
    # ElevenLabs' VAD occasionally commits a segment with no recognized
    # speech (silence, noise) - an empty or whitespace-only text, not a
    # missing one. These must never reach the client, DeepL, or Supabase.
    canned = [
        {"message_type": "committed_transcript", "text": ""},
        {"message_type": "committed_transcript", "text": "   "},
        {"message_type": "committed_transcript", "text": "hello"},
    ]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        }
        ws.send_json({"type": "stop_transcription"})

    saved = [m for m in fake_supabase.messages if m["session_id"] == session_id]
    assert len(saved) == 1
    assert saved[0]["original_text"] == "hello"


def test_audio_chunks_are_forwarded_to_the_session(monkeypatch, joined_ws):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription"})
        ws.send_bytes(b"\x00\x01" * 10)
        ws.send_json({"type": "stop_transcription"})

    assert fake_cls.instances[0].audio_chunks == [b"\x00\x01" * 10]


def test_stop_transcription_closes_the_session(monkeypatch, joined_ws):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}

    assert fake_cls.instances[0].closed is True


def test_stop_transcription_does_not_end_the_session(monkeypatch, joined_ws, fake_supabase):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}
        # Checked before the connection closes below - closing it ends the
        # session (see test_disconnecting_ends_the_session_exactly_once).
        assert fake_supabase.sessions[session_id]["ended_at"] is None


def test_disconnecting_ends_the_session_exactly_once(monkeypatch, joined_ws, fake_supabase):
    end_calls: list[str] = []
    real_end_session = fake_supabase.end_session

    async def counting_end_session(user, session_id):
        end_calls.append(session_id)
        await real_end_session(user, session_id)

    monkeypatch.setattr("routers.ws.supabase.end_session", counting_end_session)

    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        # Two pause/resume cycles before disconnecting - neither stop should
        # end the session.
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})

    assert end_calls == [session_id]
    assert fake_supabase.sessions[session_id]["ended_at"] is not None


def test_duplicate_start_transcription_is_ignored(monkeypatch, joined_ws):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "message", "text": "ok"})
        assert ws.receive_json() == {"type": "echo", "text": "ok"}

    assert len(fake_cls.instances) == 1


def test_start_transcription_never_calls_create_session(monkeypatch, joined_ws):
    async def unexpected_create_session(*args, **kwargs):
        raise AssertionError("create_session should never be called - sessions come from the REST API")

    monkeypatch.setattr("routers.ws.supabase.create_session", unexpected_create_session)

    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})


def test_committed_transcripts_are_saved_with_incrementing_sequence(
    monkeypatch, joined_ws, fake_supabase
):
    canned = [
        {"message_type": "committed_transcript", "text": "hello"},
        {"message_type": "committed_transcript", "text": "world"},
    ]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    saved = [m for m in fake_supabase.messages if m["session_id"] == session_id]
    assert [m["sequence"] for m in saved] == [0, 1]
    assert [m["original_text"] for m in saved] == ["hello", "world"]


def test_pausing_and_resuming_saves_messages_to_the_same_session_with_incrementing_sequence(
    monkeypatch, joined_ws, fake_supabase
):
    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()  # "hello"
        ws.send_json({"type": "stop_transcription"})

        # A second recording (pause/resume, not a new join) in the same
        # connection commits "world" - the fake session class's events()
        # reads canned live, so mutating it in place feeds the resumed
        # recording a different transcript.
        canned.clear()
        canned.append({"message_type": "committed_transcript", "text": "world"})

        ws.send_json({"type": "start_transcription"})
        ws.receive_json()  # "world"
        ws.send_json({"type": "stop_transcription"})

    saved = [m for m in fake_supabase.messages if m["session_id"] == session_id]
    assert [m["sequence"] for m in saved] == [0, 1]
    assert [m["original_text"] for m in saved] == ["hello", "world"]


def test_partial_transcripts_are_not_persisted(monkeypatch, joined_ws, fake_supabase):
    canned = [{"message_type": "partial_transcript", "text": "hel"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    assert [m for m in fake_supabase.messages if m["session_id"] == session_id] == []


def test_save_message_failure_does_not_break_transcription(monkeypatch, joined_ws):
    async def failing_save_message(
        user, session_id, sequence, original_text, translated_text=None, target_language=None
    ):
        raise RuntimeError("supabase is down")

    monkeypatch.setattr("routers.ws.supabase.save_message", failing_save_message)

    canned = [{"message_type": "committed_transcript", "text": "still works"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "still works",
            "translated_text": None,
            "target_language": None,
        }
        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "message", "text": "ok"})
        assert ws.receive_json() == {"type": "echo", "text": "ok"}


def test_without_a_target_language_deepl_is_not_called(monkeypatch, joined_ws):
    async def unexpected_translate(text, target_language):
        raise AssertionError("deepl.translate should not be called with no target language set")

    monkeypatch.setattr("routers.ws.deepl.translate", unexpected_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        }
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_triggers_translation_on_the_next_committed_transcript(
    monkeypatch, joined_ws
):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": "[es] hello",
            "target_language": "es",
        }
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_change_retranslates_already_committed_transcripts(monkeypatch, joined_ws):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": "[es] hello",
            "target_language": "es",
        }

        ws.send_json({"type": "set_target_language", "target_language": "fr"})
        assert ws.receive_json() == {
            "type": "retranslated_transcripts",
            "target_language": "fr",
            "transcripts": [
                {
                    "type": "transcript",
                    "original_text": "hello",
                    "translated_text": "[fr] hello",
                    "target_language": "fr",
                }
            ],
        }
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_to_the_same_value_does_not_retranslate(monkeypatch, joined_ws):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()  # the original transcript

        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_equal_to_the_seeded_language_does_not_retranslate(
    fake_supabase, authenticated_ws
):
    session_id = fake_supabase.seed_session(target_language="es", messages=["hello"])

    with authenticated_ws() as ws:
        ws.send_json({"type": "join_session", "session_id": session_id})
        ws.receive_json()  # session_joined

        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}


def test_set_target_language_with_no_committed_transcripts_yet_does_not_retranslate(joined_ws):
    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "set_target_language", "target_language": "fr"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}


def test_retranslation_does_not_block_the_receive_loop(monkeypatch, joined_ws):
    async def slow_translate(text, target_language):
        await asyncio.sleep(0.3)
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", slow_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()  # original transcript, untranslated (no target language set yet)

        ws.send_json({"type": "set_target_language", "target_language": "es"})
        started = time.monotonic()
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}
        # The echo must not wait behind the slow retranslation - it should come
        # back almost immediately, well under the translate call's 0.3s delay.
        assert time.monotonic() - started < 0.15
        ws.send_json({"type": "stop_transcription"})


def test_a_later_target_language_change_supersedes_an_in_flight_retranslation(monkeypatch, joined_ws):
    async def slow_translate(text, target_language):
        delay = {"de": 0.15, "es": 0.02}[target_language]
        await asyncio.sleep(delay)
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", slow_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()  # original transcript, untranslated

        ws.send_json({"type": "set_target_language", "target_language": "de"})
        ws.send_json({"type": "set_target_language", "target_language": "es"})

        # Only the latest ("es") retranslation should ever be sent - the
        # slower, now-superseded "de" one must be dropped, not just delayed.
        assert ws.receive_json() == {
            "type": "retranslated_transcripts",
            "target_language": "es",
            "transcripts": [
                {
                    "type": "transcript",
                    "original_text": "hello",
                    "translated_text": "[es] hello",
                    "target_language": "es",
                }
            ],
        }

        # Wait past "de"'s slower delay to prove its stale result never
        # arrives afterward either.
        time.sleep(0.2)
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_after_join_retranslates_stored_and_new_lines_together(
    monkeypatch, fake_supabase, authenticated_ws
):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    session_id = fake_supabase.seed_session(messages=["hello"])
    canned = [{"message_type": "committed_transcript", "text": "world"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "join_session", "session_id": session_id})
        ws.receive_json()  # session_joined

        ws.send_json({"type": "start_transcription"})
        ws.receive_json()  # "world", untranslated (no target language yet)

        ws.send_json({"type": "set_target_language", "target_language": "es"})
        assert ws.receive_json() == {
            "type": "retranslated_transcripts",
            "target_language": "es",
            "transcripts": [
                {
                    "type": "transcript",
                    "original_text": "hello",
                    "translated_text": "[es] hello",
                    "target_language": "es",
                },
                {
                    "type": "transcript",
                    "original_text": "world",
                    "translated_text": "[es] world",
                    "target_language": "es",
                },
            ],
        }
        ws.send_json({"type": "stop_transcription"})


async def test_a_transcript_committed_during_retranslation_is_included_in_the_result(monkeypatch):
    from routers.ws import ConnectionHandler

    sent: list[dict] = []

    class FakeWebSocket:
        async def send_json(self, payload):
            sent.append(payload)

    handler = ConnectionHandler(FakeWebSocket())
    handler.committed_texts = ["hello"]
    handler.target_language = "es"

    async def slow_translate(text, target_language):
        if text == "hello":
            # Simulate a normal committed transcript arriving on the main
            # receive loop while this retranslation of "hello" is in flight.
            await handler._handle_committed_transcript("world")
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", slow_translate)

    await handler._retranslate_committed_texts("es", handler._retranslation_generation)

    # "world" was already sent once via the normal path...
    assert sent[0] == {
        "type": "transcript",
        "original_text": "world",
        "translated_text": "[es] world",
        "target_language": "es",
    }
    # ...and the wholesale-replacing retranslated_transcripts result must
    # still include it - dropping it here would erase it from the screen
    # even though it was just correctly delivered.
    assert sent[1] == {
        "type": "retranslated_transcripts",
        "target_language": "es",
        "transcripts": [
            {
                "type": "transcript",
                "original_text": "hello",
                "translated_text": "[es] hello",
                "target_language": "es",
            },
            {
                "type": "transcript",
                "original_text": "world",
                "translated_text": "[es] world",
                "target_language": "es",
            },
        ],
    }


async def test_a_superseded_retranslation_stops_calling_deepl_early(monkeypatch):
    from routers.ws import ConnectionHandler

    sent: list[dict] = []

    class FakeWebSocket:
        async def send_json(self, payload):
            sent.append(payload)

    handler = ConnectionHandler(FakeWebSocket())
    handler.committed_texts = ["one", "two", "three"]
    handler.target_language = "es"
    handler._retranslation_generation = 1

    translated: list[str] = []

    async def translate_and_supersede(text, target_language):
        translated.append(text)
        if text == "one":
            # Simulate a further language change landing while this
            # translation is still in flight.
            handler._retranslation_generation = 2
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", translate_and_supersede)

    await handler._retranslate_committed_texts("es", 1)

    # "two" and "three" must never reach DeepL once superseded, and no
    # (now-stale) result should be sent either.
    assert translated == ["one"]
    assert sent == []


def test_set_target_language_is_invalid_without_a_target_language(joined_ws):
    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "set_target_language"})
        error = ws.receive_json()
        assert error["type"] == "error"


def test_deepl_failure_does_not_crash_the_socket_and_translated_text_stays_null(monkeypatch, joined_ws):
    async def failing_translate(text, target_language):
        raise RuntimeError("deepl is down")

    monkeypatch.setattr("routers.ws.deepl.translate", failing_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": None,
            "target_language": "es",
        }
        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}


async def test_committed_transcript_uses_the_target_language_captured_at_dispatch_time(monkeypatch):
    from routers.ws import ConnectionHandler

    sent: list[dict] = []

    class FakeWebSocket:
        async def send_json(self, payload):
            sent.append(payload)

    handler = ConnectionHandler(FakeWebSocket())
    handler.target_language = "es"

    async def translate_then_mutate(text, target_language):
        # Simulate a set_target_language message arriving on the main receive
        # loop while this translation is still in flight.
        handler.target_language = "fr"
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", translate_then_mutate)

    await handler._handle_committed_transcript("hello")

    assert sent[0]["target_language"] == "es"
    assert sent[0]["translated_text"] == "[es] hello"
    assert handler.target_language == "fr"


async def test_committed_transcript_is_saved_even_if_sending_it_to_the_client_fails(fake_supabase):
    from routers.ws import ConnectionHandler

    class DisconnectingWebSocket:
        async def send_json(self, payload):
            # A real client that has already disconnected: the socket write
            # itself fails, which Starlette surfaces as WebSocketDisconnect.
            raise WebSocketDisconnect(code=1006)

    handler = ConnectionHandler(DisconnectingWebSocket())
    handler.user = DEFAULT_USER
    handler.db_session_id = "session-1"

    await handler._handle_committed_transcript("hello")

    assert len(fake_supabase.messages) == 1
    assert fake_supabase.messages[0]["original_text"] == "hello"


def test_translation_does_not_block_relaying_further_events(monkeypatch, joined_ws):
    async def slow_translate(text, target_language):
        await asyncio.sleep(0.2)
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", slow_translate)

    canned = [
        {"message_type": "committed_transcript", "text": "hello"},
        {"message_type": "partial_transcript", "text": "world in progress"},
    ]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        # Queued right after the slow committed_transcript - must not wait for
        # that translation to resolve first.
        assert ws.receive_json() == {"type": "partial_transcript", "text": "world in progress"}
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": "[es] hello",
            "target_language": "es",
        }
        ws.send_json({"type": "stop_transcription"})


def test_start_transcription_with_an_invalid_payload_returns_error_and_does_not_start(
    monkeypatch, joined_ws
):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription", "source_language": {"bad": "shape"}})
        error = ws.receive_json()
        assert error["type"] == "error"

        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}

    assert fake_cls.instances == []


def test_set_target_language_rejects_an_unsupported_code(monkeypatch, joined_ws):
    async def unexpected_translate(text, target_language):
        raise AssertionError("should not translate with a rejected target language")

    monkeypatch.setattr("routers.ws.deepl.translate", unexpected_translate)
    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "set_target_language", "target_language": "xx"})
        error = ws.receive_json()
        assert error["type"] == "error"

        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        }
        ws.send_json({"type": "stop_transcription"})


def test_start_transcription_persists_the_source_language(monkeypatch, joined_ws, fake_supabase):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        ws.send_json({"type": "start_transcription", "source_language": "es"})
        ws.send_json({"type": "stop_transcription"})

    assert fake_supabase.sessions[session_id]["source_language"] == "es"


def test_start_transcription_with_no_source_language_leaves_it_unset(
    monkeypatch, joined_ws, fake_supabase
):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})

    assert fake_supabase.sessions[session_id]["source_language"] is None


def test_set_target_language_updates_the_persisted_session_mid_recording(
    monkeypatch, joined_ws, fake_supabase
):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        ws.send_json({"type": "start_transcription"})
        assert fake_supabase.sessions[session_id]["target_language"] is None

        ws.send_json({"type": "set_target_language", "target_language": "de"})
        ws.send_json({"type": "stop_transcription"})

    assert fake_supabase.sessions[session_id]["target_language"] == "de"


def test_set_target_language_persistence_does_not_block_the_receive_loop(monkeypatch, joined_ws):
    async def slow_update(user, session_id, target_language):
        await asyncio.sleep(0.3)

    monkeypatch.setattr("routers.ws.supabase.update_session_target_language", slow_update)

    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        started = time.monotonic()
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}
        # The echo must not wait behind the slow Supabase write - it should come
        # back almost immediately, well under the write's 0.3s delay.
        assert time.monotonic() - started < 0.15
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_persistence_failure_does_not_crash_the_socket(monkeypatch, joined_ws):
    async def failing_update(user, session_id, target_language):
        raise RuntimeError("supabase is down")

    monkeypatch.setattr("routers.ws.supabase.update_session_target_language", failing_update)

    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, _session_id):
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "set_target_language", "target_language": "de"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}
        ws.send_json({"type": "stop_transcription"})


def test_committed_transcript_persists_translated_text_and_target_language(
    monkeypatch, joined_ws, fake_supabase
):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    saved = next(m for m in fake_supabase.messages if m["session_id"] == session_id)
    assert saved["translated_text"] == "[es] hello"
    assert saved["target_language"] == "es"


def test_committed_transcript_with_no_target_language_persists_null_translation(
    monkeypatch, joined_ws, fake_supabase
):
    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    saved = next(m for m in fake_supabase.messages if m["session_id"] == session_id)
    assert saved["translated_text"] is None


# ── live room (KAN-50/KAN-54) ───────────────────────────────────────────


class FakeViewer:
    def __init__(self):
        self.received: list[dict] = []

    async def send(self, payload: dict) -> None:
        self.received.append(payload)


@pytest.fixture(autouse=True)
def _reset_live_room_registry():
    # A module-level singleton (services.live_rooms.registry) - cleared
    # around every test so a leftover room from one test can't leak into
    # the next.
    live_rooms.registry._rooms.clear()
    yield
    live_rooms.registry._rooms.clear()


def test_join_session_acquires_a_live_room_keyed_by_share_token(joined_ws, fake_supabase):
    with joined_ws() as (ws, session_id):
        share_token = fake_supabase.sessions[session_id]["share_token"]
        room = live_rooms.registry.get(share_token)
        assert room is not None
        assert room.session_id == session_id
        assert room.refcount == 1


def test_starting_and_stopping_transcription_broadcasts_room_status(
    monkeypatch, joined_ws, fake_supabase
):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        share_token = fake_supabase.sessions[session_id]["share_token"]
        room = live_rooms.registry.get(share_token)
        assert room.state == "paused"

        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "message", "text": "sync"})
        assert ws.receive_json() == {"type": "echo", "text": "sync"}
        assert room.state == "recording"

        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "message", "text": "sync"})
        assert ws.receive_json() == {"type": "echo", "text": "sync"}
        assert room.state == "paused"


def test_disconnect_broadcasts_ended_status_and_releases_the_room(joined_ws, fake_supabase):
    with joined_ws() as (ws, session_id):
        share_token = fake_supabase.sessions[session_id]["share_token"]
        room = live_rooms.registry.get(share_token)
        viewer = FakeViewer()
        room.add_viewer(viewer, "fr")

    assert live_rooms.registry.get(share_token) is None
    assert viewer.received[-1] == {"type": "live_status", "state": "ended"}


def test_committed_transcript_is_published_to_room_viewers(monkeypatch, joined_ws, fake_supabase):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hola"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        share_token = fake_supabase.sessions[session_id]["share_token"]
        room = live_rooms.registry.get(share_token)
        viewer = FakeViewer()
        room.add_viewer(viewer, "es")

        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hola",
            "translated_text": None,
            "target_language": None,
        }
        # Synchronization barrier: the room worker is a separate asyncio
        # task fed by a non-blocking queue, not awaited inline by the
        # message handler - give it a couple of round trips to finish.
        ws.send_json({"type": "message", "text": "sync"})
        assert ws.receive_json() == {"type": "echo", "text": "sync"}
        ws.send_json({"type": "stop_transcription"})

    lines = [m for m in viewer.received if m["type"] == "live_line"]
    assert lines == [
        {
            "type": "live_line",
            "index": 0,
            "original_text": "hola",
            "translated_text": "[es] hola",
            "target_language": "es",
        }
    ]


def test_publishing_to_the_room_never_blocks_saving_or_sending_the_owners_own_transcript(
    monkeypatch, joined_ws, fake_supabase
):
    # A viewer whose translation would hang forever must not stall the
    # owner's own transcript getting saved and echoed back.
    hung = asyncio.Event()

    async def hanging_translate(text, target_language):
        await hung.wait()
        return "never"

    monkeypatch.setattr("routers.ws.deepl.translate", hanging_translate)

    canned = [{"message_type": "committed_transcript", "text": "hola"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (ws, session_id):
        share_token = fake_supabase.sessions[session_id]["share_token"]
        room = live_rooms.registry.get(share_token)
        room.add_viewer(FakeViewer(), "de")

        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hola",
            "translated_text": None,
            "target_language": None,
        }
        ws.send_json({"type": "stop_transcription"})

    saved = [m for m in fake_supabase.messages if m["session_id"] == session_id]
    assert [m["original_text"] for m in saved] == ["hola"]


def test_end_to_end_a_real_viewer_socket_receives_the_owners_committed_transcript(
    monkeypatch, joined_ws, fake_supabase
):
    # Exercises the full path through a real /ws/view connection (KAN-55),
    # not a FakeViewer - owner /ws and viewer /ws/view are two independent
    # endpoints (docs/decisions.md D1) meeting only through the LiveRoom
    # registry.
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hola"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with joined_ws() as (owner_ws, session_id):
        share_token = fake_supabase.sessions[session_id]["share_token"]

        with client.websocket_connect("/ws/view") as viewer_ws:
            viewer_ws.send_json(
                {"type": "join_live", "share_token": share_token, "target_language": "fr"}
            )
            joined = viewer_ws.receive_json()
            assert joined == {
                "type": "live_joined",
                "title": "Test session",
                "source_language": None,
                "target_language": "fr",
                "state": "paused",
                "lines": [],
            }

            owner_ws.send_json({"type": "start_transcription"})
            assert viewer_ws.receive_json() == {"type": "live_status", "state": "recording"}
            assert owner_ws.receive_json() == {
                "type": "transcript",
                "original_text": "hola",
                "translated_text": None,
                "target_language": None,
            }
            assert viewer_ws.receive_json() == {
                "type": "live_line",
                "index": 0,
                "original_text": "hola",
                "translated_text": "[fr] hola",
                "target_language": "fr",
            }

            owner_ws.send_json({"type": "stop_transcription"})
            assert viewer_ws.receive_json() == {"type": "live_status", "state": "paused"}
    # (the "ended" broadcast on owner disconnect is covered separately by
    # test_disconnect_broadcasts_ended_status_and_releases_the_room, which
    # doesn't need to juggle two real sockets' close ordering to observe it)
