import pytest

from services import tts_cache
from services.auth import AuthenticatedUser


def user():
    return AuthenticatedUser(id="owner-1", email="a@example.com", access_token="tok-a")


@pytest.fixture
def fake_backends(monkeypatch):
    calls = {"synthesize": [], "upload_audio": [], "get_signed_url": [], "create_message_audio": []}
    cached: dict[tuple[str, str], dict] = {}

    async def fake_get_message_audio(user, message_id, language):
        return cached.get((message_id, language))

    async def fake_create_message_audio(user, message_id, language, storage_path):
        row = {"message_id": message_id, "language": language, "storage_path": storage_path}
        cached[(message_id, language)] = row
        calls["create_message_audio"].append(row)
        return row

    async def fake_synthesize(text):
        calls["synthesize"].append(text)
        return b"audio-bytes"

    async def fake_upload_audio(user, storage_path, audio_bytes):
        calls["upload_audio"].append((storage_path, audio_bytes))

    async def fake_get_signed_url(user, storage_path):
        calls["get_signed_url"].append(storage_path)
        return f"https://signed.example/{storage_path}"

    monkeypatch.setattr("services.tts_cache.supabase.get_message_audio", fake_get_message_audio)
    monkeypatch.setattr("services.tts_cache.supabase.create_message_audio", fake_create_message_audio)
    monkeypatch.setattr("services.tts_cache.elevenlabs.synthesize", fake_synthesize)
    monkeypatch.setattr("services.tts_cache.storage.upload_audio", fake_upload_audio)
    monkeypatch.setattr("services.tts_cache.storage.get_signed_url", fake_get_signed_url)

    return calls


async def test_a_cache_miss_synthesizes_uploads_and_caches(fake_backends):
    url = await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "fr")

    assert fake_backends["synthesize"] == ["hola"]
    assert fake_backends["upload_audio"] == [("owner-1/session-1/message-1.fr.mp3", b"audio-bytes")]
    assert fake_backends["create_message_audio"] == [
        {
            "message_id": "message-1",
            "language": "fr",
            "storage_path": "owner-1/session-1/message-1.fr.mp3",
        }
    ]
    assert url == "https://signed.example/owner-1/session-1/message-1.fr.mp3"


async def test_a_cache_hit_never_calls_synthesize_or_upload_again(fake_backends):
    await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "fr")
    url = await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "fr")

    assert fake_backends["synthesize"] == ["hola"]
    assert fake_backends["upload_audio"] == [("owner-1/session-1/message-1.fr.mp3", b"audio-bytes")]
    assert url == "https://signed.example/owner-1/session-1/message-1.fr.mp3"


async def test_different_languages_for_the_same_message_are_cached_separately(fake_backends):
    await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "fr")
    await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "de")

    assert fake_backends["synthesize"] == ["hola", "hola"]
    assert len(fake_backends["create_message_audio"]) == 2
