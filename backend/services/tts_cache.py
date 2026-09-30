from services import elevenlabs, storage, supabase
from services.auth import AuthenticatedUser


async def get_or_create_audio_url(
    user: AuthenticatedUser,
    session_id: str,
    message_id: str,
    text: str,
    language: str,
) -> str:
    # A cache hit costs one Postgres read + one Storage sign; a miss also
    # costs one paid ElevenLabs call and one Storage upload - callers (a
    # viewer's request_audio, an owner's history play button) never call
    # synthesize() more than once per (message, language), which is the
    # whole point of keying on it (see migration 006's header / D5).
    existing = await supabase.get_message_audio(user, message_id, language)
    if existing is not None:
        return await storage.get_signed_url(user, existing["storage_path"])

    audio_bytes = await elevenlabs.synthesize(text)
    storage_path = storage.audio_storage_path(user.id, session_id, message_id, language)
    await storage.upload_audio(user, storage_path, audio_bytes)
    await supabase.create_message_audio(user, message_id, language, storage_path)
    return await storage.get_signed_url(user, storage_path)
