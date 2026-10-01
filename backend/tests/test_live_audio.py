from fastapi.testclient import TestClient

from main import app
from services import live_audio
from services.live_audio import LiveAudioStore

client = TestClient(app)

AUDIO = bytes(range(256)) * 4  # 1024 bytes, each position distinguishable


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_a_stored_clip_can_be_read_back_by_its_token():
    store = LiveAudioStore()
    token = store.put(AUDIO)
    assert store.get(token) == AUDIO


def test_tokens_are_unguessable_and_unique():
    store = LiveAudioStore()
    first, second = store.put(AUDIO), store.put(AUDIO)
    assert first != second
    assert len(first) >= 32


def test_an_unknown_token_returns_nothing():
    assert LiveAudioStore().get("nope") is None


def test_a_clip_expires_after_its_ttl():
    clock = FakeClock()
    store = LiveAudioStore(ttl_seconds=60, clock=clock)
    token = store.put(AUDIO)
    clock.now += 59
    assert store.get(token) == AUDIO
    clock.now += 2
    assert store.get(token) is None


def test_the_oldest_clips_are_dropped_past_the_bound():
    store = LiveAudioStore(max_entries=2)
    first = store.put(b"one")
    second = store.put(b"two")
    third = store.put(b"three")
    assert store.get(first) is None
    assert store.get(second) == b"two"
    assert store.get(third) == b"three"


def test_the_url_is_same_origin_and_relative():
    # Relative, so it goes through the Vite proxy on localhost, the LAN and
    # a tunnel alike (KAN-66) - never an absolute backend address.
    assert live_audio.live_audio_url("abc") == "/api/live-audio/abc"


def test_the_endpoint_serves_the_clip_as_mp3(monkeypatch):
    store = LiveAudioStore()
    monkeypatch.setattr(live_audio, "store", store)
    token = store.put(AUDIO)

    response = client.get(f"/api/live-audio/{token}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == AUDIO


def test_the_endpoint_honours_a_byte_range(monkeypatch):
    # iOS Safari only plays media from servers that answer Range requests
    # with 206 - its first request is typically bytes=0-1.
    store = LiveAudioStore()
    monkeypatch.setattr(live_audio, "store", store)
    token = store.put(AUDIO)

    response = client.get(f"/api/live-audio/{token}", headers={"Range": "bytes=0-1"})

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 0-1/{len(AUDIO)}"
    assert response.content == AUDIO[0:2]


def test_the_endpoint_handles_open_ended_and_suffix_ranges(monkeypatch):
    store = LiveAudioStore()
    monkeypatch.setattr(live_audio, "store", store)
    token = store.put(AUDIO)

    open_ended = client.get(f"/api/live-audio/{token}", headers={"Range": "bytes=1000-"})
    assert open_ended.status_code == 206
    assert open_ended.headers["content-range"] == f"bytes 1000-1023/{len(AUDIO)}"
    assert open_ended.content == AUDIO[1000:]

    suffix = client.get(f"/api/live-audio/{token}", headers={"Range": "bytes=-4"})
    assert suffix.status_code == 206
    assert suffix.content == AUDIO[-4:]


def test_an_unsatisfiable_range_is_rejected(monkeypatch):
    store = LiveAudioStore()
    monkeypatch.setattr(live_audio, "store", store)
    token = store.put(AUDIO)

    response = client.get(f"/api/live-audio/{token}", headers={"Range": "bytes=5000-6000"})

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(AUDIO)}"


def test_a_malformed_range_is_ignored_and_the_whole_clip_served(monkeypatch):
    store = LiveAudioStore()
    monkeypatch.setattr(live_audio, "store", store)
    token = store.put(AUDIO)

    response = client.get(f"/api/live-audio/{token}", headers={"Range": "lines=1-2"})

    assert response.status_code == 200
    assert response.content == AUDIO


def test_an_unknown_or_expired_token_is_a_404():
    response = client.get("/api/live-audio/does-not-exist")
    assert response.status_code == 404
