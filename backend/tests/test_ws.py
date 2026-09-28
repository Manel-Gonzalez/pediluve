import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fake_supabase(monkeypatch):
    state = {"sessions": {}, "messages": []}
    counter = {"n": 0}

    async def fake_create_session(target_language="en"):
        counter["n"] += 1
        session_id = f"session-{counter['n']}"
        state["sessions"][session_id] = {"target_language": target_language, "ended_at": None}
        return session_id

    async def fake_save_message(session_id, sequence, original_text):
        state["messages"].append(
            {"session_id": session_id, "sequence": sequence, "original_text": original_text}
        )

    async def fake_end_session(session_id):
        state["sessions"][session_id]["ended_at"] = "now"

    monkeypatch.setattr("routers.ws.supabase.create_session", fake_create_session)
    monkeypatch.setattr("routers.ws.supabase.save_message", fake_save_message)
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


def test_echo_roundtrip():
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "message", "text": "hola"})
        assert ws.receive_json() == {"type": "echo", "text": "hola"}


def test_invalid_json_returns_error_and_keeps_socket_open():
    with client.websocket_connect("/ws") as ws:
        ws.send_text("not json")
        error = ws.receive_json()
        assert error["type"] == "error"

        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}


def test_unknown_message_type_returns_error():
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "not_a_real_type"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "not_a_real_type" in error["message"]


def test_start_transcription_relays_partial_and_committed_events(monkeypatch):
    canned = [
        {"message_type": "session_started", "session_id": "abc"},
        {"message_type": "partial_transcript", "text": "hel"},
        {"message_type": "committed_transcript", "text": "hello"},
    ]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start_transcription", "audio_format": "pcm_16000"})
        assert ws.receive_json() == {"type": "partial_transcript", "text": "hel"}
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        }

    assert fake_cls.instances[0].audio_format == "pcm_16000"


def test_audio_chunks_are_forwarded_to_the_session(monkeypatch):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_bytes(b"\x00\x01" * 10)
        ws.send_json({"type": "stop_transcription"})

    assert fake_cls.instances[0].audio_chunks == [b"\x00\x01" * 10]


def test_stop_transcription_closes_the_session(monkeypatch):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "message", "text": "still alive"})
        assert ws.receive_json() == {"type": "echo", "text": "still alive"}

    assert fake_cls.instances[0].closed is True


def test_duplicate_start_transcription_is_ignored(monkeypatch):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})
        ws.send_json({"type": "message", "text": "ok"})
        assert ws.receive_json() == {"type": "echo", "text": "ok"}

    assert len(fake_cls.instances) == 1


def test_start_transcription_creates_a_supabase_session(monkeypatch, fake_supabase):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})

    assert len(fake_supabase["sessions"]) == 1


def test_committed_transcripts_are_saved_with_incrementing_sequence(monkeypatch, fake_supabase):
    canned = [
        {"message_type": "committed_transcript", "text": "hello"},
        {"message_type": "committed_transcript", "text": "world"},
    ]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    assert [m["sequence"] for m in fake_supabase["messages"]] == [0, 1]
    assert [m["original_text"] for m in fake_supabase["messages"]] == ["hello", "world"]
    session_id = next(iter(fake_supabase["sessions"]))
    assert all(m["session_id"] == session_id for m in fake_supabase["messages"])


def test_partial_transcripts_are_not_persisted(monkeypatch, fake_supabase):
    canned = [{"message_type": "partial_transcript", "text": "hel"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start_transcription"})
        ws.receive_json()
        ws.send_json({"type": "stop_transcription"})

    assert fake_supabase["messages"] == []


def test_stop_transcription_marks_the_session_ended(monkeypatch, fake_supabase):
    fake_cls = make_fake_session_class([])
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start_transcription"})
        ws.send_json({"type": "stop_transcription"})

    session_id = next(iter(fake_supabase["sessions"]))
    assert fake_supabase["sessions"][session_id]["ended_at"] is not None


def test_supabase_failure_does_not_break_transcription(monkeypatch):
    async def failing_create_session(target_language="en"):
        raise RuntimeError("supabase is down")

    monkeypatch.setattr("routers.ws.supabase.create_session", failing_create_session)

    canned = [{"message_type": "committed_transcript", "text": "still works"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
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


def test_without_a_target_language_deepl_is_not_called(monkeypatch):
    async def unexpected_translate(text, target_language):
        raise AssertionError("deepl.translate should not be called with no target language set")

    monkeypatch.setattr("routers.ws.deepl.translate", unexpected_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": None,
            "target_language": None,
        }
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_triggers_translation_on_the_next_committed_transcript(monkeypatch):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    monkeypatch.setattr("routers.ws.deepl.translate", fake_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "set_target_language", "target_language": "es"})
        ws.send_json({"type": "start_transcription"})
        assert ws.receive_json() == {
            "type": "transcript",
            "original_text": "hello",
            "translated_text": "[es] hello",
            "target_language": "es",
        }
        ws.send_json({"type": "stop_transcription"})


def test_set_target_language_is_invalid_without_a_target_language():
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "set_target_language"})
        error = ws.receive_json()
        assert error["type"] == "error"


def test_deepl_failure_does_not_crash_the_socket_and_translated_text_stays_null(monkeypatch):
    async def failing_translate(text, target_language):
        raise RuntimeError("deepl is down")

    monkeypatch.setattr("routers.ws.deepl.translate", failing_translate)

    canned = [{"message_type": "committed_transcript", "text": "hello"}]
    fake_cls = make_fake_session_class(canned)
    monkeypatch.setattr("routers.ws.RealtimeTranscriptionSession", fake_cls)

    with client.websocket_connect("/ws") as ws:
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
