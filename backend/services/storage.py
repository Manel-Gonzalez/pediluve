from services.auth import AuthenticatedUser
from services.supabase import client_for

AUDIO_BUCKET = "message-audio"

# Long enough for a live demo/session without re-signing on every play;
# request_audio (KAN-58) always asks fresh rather than caching this
# client-side, so a shorter value would just mean more re-signs, not
# broken links.
SIGNED_URL_EXPIRY_SECONDS = 60 * 60


def audio_storage_path(owner_id: str, session_id: str, message_id: str, language: str) -> str:
    # {owner_id}/{session_id}/{message_id}.{language}.mp3 - owner-prefixed so
    # the storage.objects RLS policies (migration 007) are a plain
    # auth.uid() check, and flat per session so delete_session_audio's
    # prefix list/remove stays a single-level Storage `list`.
    return f"{owner_id}/{session_id}/{message_id}.{language}.mp3"


async def upload_audio(user: AuthenticatedUser, storage_path: str, audio_bytes: bytes) -> None:
    client = await client_for(user.access_token)
    try:
        await client.storage.from_(AUDIO_BUCKET).upload(
            storage_path, audio_bytes, {"content-type": "audio/mpeg", "upsert": "true"}
        )
    finally:
        await client.postgrest.aclose()


async def get_signed_url(user: AuthenticatedUser, storage_path: str) -> str:
    client = await client_for(user.access_token)
    try:
        result = await client.storage.from_(AUDIO_BUCKET).create_signed_url(
            storage_path, SIGNED_URL_EXPIRY_SECONDS
        )
        return result["signedURL"]
    finally:
        await client.postgrest.aclose()


async def delete_session_audio(user: AuthenticatedUser, owner_id: str, session_id: str) -> None:
    # Called before the session row itself is deleted (KAN-32) - the DB
    # cascade removes message_audio's rows on its own, but Storage objects
    # aren't part of that cascade and would otherwise be orphaned forever.
    prefix = f"{owner_id}/{session_id}"
    client = await client_for(user.access_token)
    try:
        files = await client.storage.from_(AUDIO_BUCKET).list(prefix)
        if not files:
            return
        paths = [f"{prefix}/{entry['name']}" for entry in files]
        await client.storage.from_(AUDIO_BUCKET).remove(paths)
    finally:
        await client.postgrest.aclose()
