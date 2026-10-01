import asyncio

import pytest

from services import live_audio, tts_cache
from services.auth import AuthenticatedUser
from services.live_audio import LiveAudioStore


def user():
    return AuthenticatedUser(id="owner-1", email="a@example.com", access_token="tok-a")


SIGNED = "https://signed.example/owner-1/session-1/message-1.{}.mp3"


async def settle():
    # Waits for the background upload + message_audio row (KAN-87).
    await asyncio.gather(*list(tts_cache._background), return_exceptions=True)


def live_clip(url):
    assert url.startswith("/api/live-audio/")
    return live_audio.store.get(url.removeprefix("/api/live-audio/"))


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
    monkeypatch.setattr("services.tts_cache.live_audio.store", LiveAudioStore())

    return calls


async def test_a_cache_miss_answers_with_the_fresh_clip_and_caches_it_in_the_background(fake_backends):
    url, cached = await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "fr")

    # KAN-87: served straight from the backend, not a signed Storage URL.
    assert live_clip(url) == b"audio-bytes"
    assert cached is False
    await settle()
    assert fake_backends["synthesize"] == ["hola"]
    assert fake_backends["upload_audio"] == [("owner-1/session-1/message-1.fr.mp3", b"audio-bytes")]
    assert fake_backends["create_message_audio"] == [
        {
            "message_id": "message-1",
            "language": "fr",
            "storage_path": "owner-1/session-1/message-1.fr.mp3",
        }
    ]
    # The listener never waits on a Storage sign for a fresh clip.
    assert fake_backends["get_signed_url"] == []


async def test_a_miss_answers_before_the_upload_finishes(fake_backends, monkeypatch):
    release = asyncio.Event()

    async def slow_upload(user, storage_path, audio_bytes):
        await release.wait()
        fake_backends["upload_audio"].append((storage_path, audio_bytes))

    monkeypatch.setattr("services.tts_cache.storage.upload_audio", slow_upload)

    url, _ = await asyncio.wait_for(
        tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "es"), timeout=1
    )
    assert live_clip(url) == b"audio-bytes"
    assert fake_backends["upload_audio"] == []

    release.set()
    await settle()
    assert len(fake_backends["upload_audio"]) == 1
    assert len(fake_backends["create_message_audio"]) == 1


async def test_a_request_while_the_upload_is_still_running_reuses_the_same_clip(fake_backends, monkeypatch):
    # Between "clip ready" and "row saved" the cache still misses - without
    # the in-flight entry staying until the row exists, this would pay for a
    # second synthesis.
    release = asyncio.Event()

    async def slow_upload(user, storage_path, audio_bytes):
        await release.wait()

    monkeypatch.setattr("services.tts_cache.storage.upload_audio", slow_upload)

    first, _ = await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "es")
    second, _ = await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "es")
    release.set()
    await settle()

    assert first == second
    assert fake_backends["synthesize"] == ["hola"]


async def test_a_failed_background_upload_is_logged_and_the_clip_still_plays(fake_backends, monkeypatch, caplog):
    async def failing_upload(user, storage_path, audio_bytes):
        raise RuntimeError("Storage is down")

    monkeypatch.setattr("services.tts_cache.storage.upload_audio", failing_upload)

    url, _ = await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "es")
    await settle()

    assert live_clip(url) == b"audio-bytes"
    assert fake_backends["create_message_audio"] == []
    assert "Could not cache audio for message message-1 (es)" in caplog.text


async def test_a_cache_hit_never_calls_synthesize_or_upload_again(fake_backends):
    await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "fr")
    await settle()
    url, cached = await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "fr")

    assert fake_backends["synthesize"] == ["hola"]
    assert fake_backends["upload_audio"] == [("owner-1/session-1/message-1.fr.mp3", b"audio-bytes")]
    assert url == SIGNED.format("fr")
    assert cached is True


async def test_different_languages_for_the_same_message_are_cached_separately(fake_backends):
    await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "fr")
    await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "de")
    await settle()

    assert fake_backends["synthesize"] == ["hola", "hola"]
    assert len(fake_backends["create_message_audio"]) == 2


async def test_concurrent_requests_for_the_same_line_share_one_generation(fake_backends, monkeypatch):
    # Two viewers in the same language asking for a brand-new line at once
    # both miss the cache. Each used to synthesize (paying twice) and upload
    # to the same path - and the second upload, an overwrite, is refused by
    # Storage RLS (migration 007 has no UPDATE policy), so one viewer got
    # "Audio unavailable" and its Listen live skipped the line.
    release = asyncio.Event()

    async def slow_synthesize(text):
        fake_backends["synthesize"].append(text)
        await release.wait()
        return b"audio-bytes"

    monkeypatch.setattr("services.tts_cache.elevenlabs.synthesize", slow_synthesize)

    first = asyncio.ensure_future(tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "es"))
    second = asyncio.ensure_future(tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "es"))
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(first, second)
    await settle()

    assert fake_backends["synthesize"] == ["hola"]
    assert len(fake_backends["upload_audio"]) == 1
    assert results[0][0] == results[1][0]
    assert live_clip(results[0][0]) == b"audio-bytes"


async def test_a_failed_generation_is_retried_by_the_next_request(fake_backends, monkeypatch):
    attempts = []

    async def flaky_synthesize(text):
        attempts.append(text)
        if len(attempts) == 1:
            raise RuntimeError("ElevenLabs is down")
        return b"audio-bytes"

    monkeypatch.setattr("services.tts_cache.elevenlabs.synthesize", flaky_synthesize)

    with pytest.raises(RuntimeError):
        await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "es")
    url, cached = await tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "es")

    assert len(attempts) == 2
    assert live_clip(url) == b"audio-bytes"
    assert cached is False


async def test_one_requester_going_away_does_not_cancel_the_generation_for_others(fake_backends, monkeypatch):
    release = asyncio.Event()

    async def slow_synthesize(text):
        fake_backends["synthesize"].append(text)
        await release.wait()
        return b"audio-bytes"

    monkeypatch.setattr("services.tts_cache.elevenlabs.synthesize", slow_synthesize)

    leaver = asyncio.ensure_future(tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "es"))
    stayer = asyncio.ensure_future(tts_cache.get_or_create_audio_url(user(), "session-1", "message-1", "hola", "es"))
    await asyncio.sleep(0)
    leaver.cancel()  # e.g. that viewer closed the page mid-generation
    release.set()

    url, _ = await stayer
    assert live_clip(url) == b"audio-bytes"
    assert fake_backends["synthesize"] == ["hola"]
