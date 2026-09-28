from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


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
        assert ws.receive_json() == {"type": "transcript", "text": "hello"}

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
