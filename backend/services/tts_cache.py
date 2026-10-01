import asyncio
import logging

from services import elevenlabs, live_audio, storage, supabase
from services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

# Generations in progress, keyed by (message_id, language), each resolving
# to the fresh clip's live URL. An entry stays until the clip is cached in
# Storage, not just until it's ready, so a request in between reuses it
# rather than paying for a second synthesis. Every room lives in this one
# process, so this is enough for concurrent misses to share one ElevenLabs
# call and one upload.
_in_flight: dict[tuple[str, str], asyncio.Future[str]] = {}
# Strong references to the background generations - the event loop itself
# only keeps weak ones, so an unreferenced task could be collected mid-way.
_background: set[asyncio.Task[None]] = set()


async def get_or_create_audio_url(
    user: AuthenticatedUser,
    session_id: str,
    message_id: str,
    text: str,
    language: str,
) -> tuple[str, bool]:
    # A cache hit costs one Postgres read + one Storage sign. A miss costs
    # one paid ElevenLabs call, and the listener only waits for that one
    # (KAN-87): the clip is served straight from the backend
    # (services/live_audio.py) while the Storage upload and the
    # message_audio row are written in the background. Keying on
    # (message, language) means synthesize() runs once per pair (see
    # migration 006's header / D5). Returns (url, cached) - cached lets a
    # caller tell "already cached" from "generated just now".
    existing = await supabase.get_message_audio(user, message_id, language)
    if existing is not None:
        return await storage.get_signed_url(user, existing["storage_path"]), True

    # Two viewers in the same language both miss the cache for a line that
    # just arrived. Without this, each synthesized it (paying twice) and
    # uploaded to the same path, and the second upload - an overwrite - is
    # refused by Storage RLS (migration 007 has no UPDATE policy), so one of
    # them got "Audio unavailable". The latecomer waits on the first instead.
    key = (message_id, language)
    clip_url = _in_flight.get(key)
    if clip_url is None:
        clip_url = asyncio.get_running_loop().create_future()
        _in_flight[key] = clip_url
        task = asyncio.ensure_future(_generate(key, clip_url, user, session_id, text))
        _background.add(task)
        task.add_done_callback(_background.discard)
    # shield(): one viewer leaving mid-generation must not cancel the clip
    # for the others still waiting on the same line.
    return await asyncio.shield(clip_url), False


async def _generate(
    key: tuple[str, str],
    clip_url: asyncio.Future[str],
    user: AuthenticatedUser,
    session_id: str,
    text: str,
) -> None:
    message_id, language = key
    try:
        try:
            audio_bytes = await elevenlabs.synthesize(text)
        except Exception as error:
            clip_url.set_exception(error)
            # Marked as retrieved, so a failure nobody is still awaiting
            # (every requester left) isn't logged as "never retrieved".
            clip_url.exception()
            return
        clip_url.set_result(live_audio.live_audio_url(live_audio.store.put(audio_bytes)))

        # Now the cache, off the listener's path. A failure here only costs
        # a future cache hit - the clip already went out - so it's logged,
        # and the next request for this line synthesizes again.
        try:
            storage_path = storage.audio_storage_path(user.id, session_id, message_id, language)
            await storage.upload_audio(user, storage_path, audio_bytes)
            await supabase.create_message_audio(user, message_id, language, storage_path)
        except Exception:
            logger.exception("Could not cache audio for message %s (%s)", message_id, language)
    finally:
        # Success or failure, the next request goes back to the cache: a hit
        # once the row exists, or a fresh attempt otherwise.
        if _in_flight.get(key) is clip_url:
            del _in_flight[key]
