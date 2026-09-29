import asyncio
import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDisconnect

from main import app
import routers.ws as ws_module
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


@pytest.fixture(autouse=True)
def fake_supabase(monkeypatch):
    state = {"sessions": {}, "messages": []}
    counter = {"n": 0}

    async def fake_create_session(user, source_language=None, target_language="en"):
        counter["n"] += 1
        session_id = f"session-{counter['n']}"
        state["sessions"][session_id] = {
            "user_id": user.id,
            "source_language": source_language,
            "target_language": target_language,
            "ended_at": None,
        }
        return session_id

    async def fake_save_message(
        user, session_id, sequence, original_text, translated_text=None, target_language=None
    ):
        state["messages"].append(
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

    async def fake_update_session_target_language(user, session_id, target_language):
        state["sessions"][session_id]["target_language"] = target_language

    async def fake_end_session(user, session_id):
        state["sessions"][session_id]["ended_at"] = "now"

    monkeypatch.setattr("routers.ws.supabase.create_session", fake_create_session)
    monkeypatch.setattr("routers.ws.supabase.save_message", fake_save_message)
    monkeypatch.setattr(
        "routers.ws.supabase.update_session_target_language", fake_update_session_target_language
    )
    monkeypatch.setattr("routers.ws.supabase.end_session", fake_end_session)
    return state


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

    with _authenticated_connection() as ws:
        # Simulates a refreshed Supabase access token arriving mid-connection.
        ws.send_json({"type": "authenticate", "access_token": REFRESHED_USER.access_token})
        assert ws.receive_json() == {"type": "authenticated", "user_id": REFRESHED_USER.id}

        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    saved = fake_supabase["messages"][0]
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

    with authenticated_ws() as ws:
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        # Disconnect immediately - before either committed transcript has been
        # relayed or saved, both still in flight behind the slow translate.

    assert len(fake_supabase["messages"]) == 2
    assert [m["original_text"] for m in fake_supabase["messages"]] == ["hello", "world"]


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


def test_start_transcription_relays_partial_and_committed_events(monkeypatch, authenticated_ws):
    canned = [
        {"message_type": "session_started", "session_id": "abc"},
        {"message_type": "partial_transcript", "text": "hel"},
        {"message_type": "committed_transcript", "text": "hello"},
    ]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription", "audio_format": "pcm_16000"})
        assert ws.receive_json() == {"type": "partial_transcript", "text": "hel"}
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        }

    assert fake_cls.instances[0].audio_format == "pcm_16000"


def test_audio_chunks_are_forwarded_to_the_session(monkeypatch, authenticated_ws):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_bytes(b"\x00\x01" * 10)
        ws.send_json({"type": "stop_transcription"})

    assert fake_cls.instances[0].audio_chunks == [b"\x00\x01" * 10]


def test_stop_transcription_closes_the_session(monkeypatch, authenticated_ws):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}

    assert fake_cls.instances[0].closed is True


def test_duplicate_start_transcription_is_ignored(monkeypatch, authenticated_ws):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "message", "text": "ok"})
        assert ws.receive_json() == {"type": "echo", "text": "ok"}

    assert len(fake_cls.instances) == 1


def test_start_transcription_creates_a_supabase_session(monkeypatch, authenticated_ws, fake_supabase):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})

    assert len(fake_supabase["sessions"]) == 1
    assert next(iter(fake_supabase["sessions"].values()))["user_id"] == DEFAULT_USER.id


def test_committed_transcripts_are_saved_with_incrementing_sequence(
    monkeypatch, authenticated_ws, fake_supabase
):
    canned = [
        {"message_type": "committed_transcript", "text": "hello"},
        {"message_type": "committed_transcript", "text": "world"},
    ]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    assert [m["sequence"] for m in fake_supabase["messages"]] == [0, 1]
    assert [m["original_text"] for m in fake_supabase["messages"]] == ["hello", "world"]
    session_id = next(iter(fake_supabase["sessions"]))
    assert all(m["session_id"] == session_id for m in fake_supabase["messages"])


def test_partial_transcripts_are_not_persisted(monkeypatch, authenticated_ws, fake_supabase):
    canned = [{"message_type": "partial_transcript", "text": "hel"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    assert fake_supabase["messages"] == []


def test_stop_transcription_marks_the_session_ended(monkeypatch, authenticated_ws, fake_supabase):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})

    session_id = next(iter(fake_supabase["sessions"]))
    assert fake_supabase["sessions"][session_id]["ended_at"] is not None


def test_supabase_failure_does_not_break_transcription(monkeypatch, authenticated_ws):
    async def failing_create_session(user, source_language=None, target_language="en"):
        raise RuntimeError("supabase is down")

    monkeypatch.setattr("routers.ws.supabase.create_session", failing_create_session)

    canned = [{"message_type": "committed_transcript", "text": "still works"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
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


def test_without_a_target_language_deepl_is_not_called(monkeypatch, authenticated_ws):
    async def unexpected_translate(text, target_language):
        raise AssertionError("deepl.translate should not be called with no target language set")

    monkeypatch.setattr("routers.ws.deepl.translate", unexpected_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        }
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_triggers_translation_on_the_next_committed_transcript(
    monkeypatch, authenticated_ws
):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": "[es] hello",
            "target_language": "es",
        }
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_change_retranslates_already_committed_transcripts(
    monkeypatch, authenticated_ws
):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
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


def test_set_target_language_to_the_same_value_does_not_retranslate(monkeypatch, authenticated_ws):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()  # the original transcript

        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_with_no_committed_transcripts_yet_does_not_retranslate(
    authenticated_ws,
):
    with authenticated_ws() as ws:
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "set_target_language", "target_language": "fr"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}


def test_retranslation_does_not_block_the_receive_loop(monkeypatch, authenticated_ws):
    async def slow_translate(text, target_language):
        await asyncio.sleep(0.3)
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", slow_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
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


def test_a_later_target_language_change_supersedes_an_in_flight_retranslation(
    monkeypatch, authenticated_ws
):
    async def slow_translate(text, target_language):
        delay = {"de": 0.15, "es": 0.02}[target_language]
        await asyncio.sleep(delay)
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", slow_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
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


def test_committed_texts_persist_across_multiple_recordings_in_the_same_connection(
    monkeypatch, authenticated_ws
):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()  # "hello", untranslated
        ws.send_json({"type": "stop_transcription"})

        # A second recording in the same connection commits "world" - the
        # fake session class's events() reads canned live, so mutating it in
        # place feeds the new session a different transcript.
        canned.clear()
        canned.append({"message_type": "committed_transcript", "text": "world"})

        ws.send_json({"type": "start_transcription"})
        ws.receive_json()  # "world", untranslated
        ws.send_json({"type": "set_target_language", "target_language": "es"})

        # Both recordings' lines must still be there - resetting committed
        # texts per recording would have silently dropped "hello" here.
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


def test_set_target_language_is_invalid_without_a_target_language(authenticated_ws):
    with authenticated_ws() as ws:
        ws.send_json({"type": "set_target_language"})
        error = ws.receive_json()
        assert error["type"] == "error"


def test_deepl_failure_does_not_crash_the_socket_and_translated_text_stays_null(
    monkeypatch, authenticated_ws
):
    async def failing_translate(text, target_language):
        raise RuntimeError("deepl is down")

    monkeypatch.setattr("routers.ws.deepl.translate", failing_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
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


async def test_committed_transcript_is_saved_even_if_sending_it_to_the_client_fails(
    fake_supabase,
):
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

    assert len(fake_supabase["messages"]) == 1
    assert fake_supabase["messages"][0]["original_text"] == "hello"


def test_translation_does_not_block_relaying_further_events(monkeypatch, authenticated_ws):
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

    with authenticated_ws() as ws:
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
    monkeypatch, authenticated_ws
):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription", "source_language": {"bad": "shape"}})
        error = ws.receive_json()
        assert error["type"] == "error"

        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}

    assert fake_cls.instances == []


def test_set_target_language_rejects_an_unsupported_code(monkeypatch, authenticated_ws):
    async def unexpected_translate(text, target_language):
        raise AssertionError("should not translate with a rejected target language")

    monkeypatch.setattr("routers.ws.deepl.translate", unexpected_translate)
    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
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


def test_start_transcription_persists_the_source_language(monkeypatch, authenticated_ws, fake_supabase):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription", "source_language": "es"})
        ws.send_json({"type": "stop_transcription"})

    session_id = next(iter(fake_supabase["sessions"]))
    assert fake_supabase["sessions"][session_id]["source_language"] == "es"


def test_start_transcription_with_no_source_language_persists_none(
    monkeypatch, authenticated_ws, fake_supabase
):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})

    session_id = next(iter(fake_supabase["sessions"]))
    assert fake_supabase["sessions"][session_id]["source_language"] is None


def test_start_transcription_persists_a_target_language_set_before_recording_started(
    monkeypatch, authenticated_ws, fake_supabase
):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "set_target_language", "target_language": "fr"})
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})

    session_id = next(iter(fake_supabase["sessions"]))
    assert fake_supabase["sessions"][session_id]["target_language"] == "fr"


def test_set_target_language_updates_the_persisted_session_mid_recording(
    monkeypatch, authenticated_ws, fake_supabase
):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        session_id = next(iter(fake_supabase["sessions"]))
        assert fake_supabase["sessions"][session_id]["target_language"] == "en"

        ws.send_json({"type": "set_target_language", "target_language": "de"})
        ws.send_json({"type": "stop_transcription"})

    assert fake_supabase["sessions"][session_id]["target_language"] == "de"


def test_set_target_language_persistence_does_not_block_the_receive_loop(
    monkeypatch, authenticated_ws, fake_supabase
):
    async def slow_update(user, session_id, target_language):
        await asyncio.sleep(0.3)

    monkeypatch.setattr("routers.ws.supabase.update_session_target_language", slow_update)

    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        started = time.monotonic()
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}
        # The echo must not wait behind the slow Supabase write - it should come
        # back almost immediately, well under the write's 0.3s delay.
        assert time.monotonic() - started < 0.15
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_persistence_failure_does_not_crash_the_socket(
    monkeypatch, authenticated_ws, fake_supabase
):
    async def failing_update(user, session_id, target_language):
        raise RuntimeError("supabase is down")

    monkeypatch.setattr("routers.ws.supabase.update_session_target_language", failing_update)

    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "set_target_language", "target_language": "de"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}
        ws.send_json({"type": "stop_transcription"})


def test_committed_transcript_persists_translated_text_and_target_language(
    monkeypatch, authenticated_ws, fake_supabase
):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    saved = fake_supabase["messages"][0]
    assert saved["translated_text"] == "[es] hello"
    assert saved["target_language"] == "es"


def test_committed_transcript_with_no_target_language_persists_null_translation(
    monkeypatch, authenticated_ws, fake_supabase
):
    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with authenticated_ws() as ws:
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    saved = fake_supabase["messages"][0]
    assert saved["translated_text"] is None
    assert saved["target_language"] is None
