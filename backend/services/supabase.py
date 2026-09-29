import os

from supabase import AsyncClient, create_async_client

# Phase 1 has no language selector yet (that's Phase 2) - sessions.target_language
# is NOT NULL, so this placeholder holds the column until Phase 2 sets a real value.
DEFAULT_TARGET_LANGUAGE = "en"

_client: AsyncClient | None = None


async def _get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await create_async_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _client


async def create_session(
    source_language: str | None = None, target_language: str = DEFAULT_TARGET_LANGUAGE
) -> str:
    client = await _get_client()
    result = (
        await client.table("sessions")
        .insert({"source_language": source_language, "target_language": target_language})
        .execute()
    )
    return result.data[0]["id"]


async def save_message(
    session_id: str,
    sequence: int,
    original_text: str,
    translated_text: str | None = None,
    target_language: str | None = None,
) -> None:
    client = await _get_client()
    await client.table("messages").insert(
        {
            "session_id": session_id,
            "sequence": sequence,
            "original_text": original_text,
            "translated_text": translated_text,
            "target_language": target_language,
        }
    ).execute()


async def update_session_target_language(session_id: str, target_language: str) -> None:
    client = await _get_client()
    await client.table("sessions").update({"target_language": target_language}).eq(
        "id", session_id
    ).execute()


async def end_session(session_id: str) -> None:
    client = await _get_client()
    # "now" (no parens) is Postgres' special date/time value, resolved by the
    # server at write time - avoids clock skew between this process and the DB.
    await client.table("sessions").update({"ended_at": "now"}).eq("id", session_id).execute()
