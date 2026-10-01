import asyncio

from services import elevenlabs, storage, supabase
from services.auth import AuthenticatedUser

# Generations in progress, keyed by (message_id, language). Every room
# lives in this one process, so this is enough to make concurrent misses
# for the same line share one ElevenLabs call and one upload.
_in_flight: dict[tuple[str, str], asyncio.Future[str]] = {}


async def get_or_create_audio_url(
    user: AuthenticatedUser,
    session_id: str,
    message_id: str,
    text: str,
    language: str,
) -> tuple[str, bool]:
    # A cache hit costs one Postgres read + one Storage sign; a miss also
    # costs one paid ElevenLabs call and one Storage upload - callers (a
    # viewer's request_audio, an owner's history play button) never call
    # synthesize() more than once per (message, language), which is the
    # whole point of keying on it (see migration 006's header / D5).
    # Returns (signed_url, cached) - cached lets a caller show "already
    # cached" vs. "generated just now" without a second lookup.
    existing = await supabase.get_message_audio(user, message_id, language)
    if existing is not None:
        return await storage.get_signed_url(user, existing["storage_path"]), True

    # Two viewers in the same language both miss the cache for a line that
    # just arrived. Without this, each synthesized it (paying twice) and
    # uploaded to the same path, and the second upload - an overwrite - is
    # refused by Storage RLS (migration 007 has no UPDATE policy), so one of
    # them got "Audio unavailable". The latecomer waits on the first instead.
    key = (message_id, language)
    generation = _in_flight.get(key)
    if generation is None:
        generation = asyncio.ensure_future(_generate(user, session_id, message_id, text, language))
        _in_flight[key] = generation
        generation.add_done_callback(lambda done: _forget(key, done))
    # shield(): one viewer leaving mid-generation must not cancel it for
    # the others still waiting on the same line.
    storage_path = await asyncio.shield(generation)
    return await storage.get_signed_url(user, storage_path), False


async def _generate(
    user: AuthenticatedUser, session_id: str, message_id: str, text: str, language: str
) -> str:
    audio_bytes = await elevenlabs.synthesize(text)
    storage_path = storage.audio_storage_path(user.id, session_id, message_id, language)
    await storage.upload_audio(user, storage_path, audio_bytes)
    await supabase.create_message_audio(user, message_id, language, storage_path)
    return storage_path


def _forget(key: tuple[str, str], done: asyncio.Future[str]) -> None:
    # Success or failure, the next request goes back to the cache: a hit
    # once the row exists, or a fresh attempt after a failure.
    if _in_flight.get(key) is done:
        del _in_flight[key]
    # Retrieved so a failure nobody is still awaiting (every requester
    # left) isn't logged as "exception was never retrieved".
    if not done.cancelled():
        done.exception()
