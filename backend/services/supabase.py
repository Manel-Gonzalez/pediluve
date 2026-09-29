import os

from supabase import AsyncClient, create_async_client

from services.auth import AuthenticatedUser

DEFAULT_TARGET_LANGUAGE = "en"


async def client_for(access_token: str) -> AsyncClient:
    # A fresh client per call, authenticated as the given user's access
    # token so RLS's auth.uid() resolves to them. Deliberately not cached/
    # shared: a single client reused across users would leak one user's
    # Authorization header onto another's requests. SUPABASE_KEY stays the
    # anon key here - the service-role key would bypass RLS entirely.
    client = await create_async_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    client.postgrest.auth(access_token)
    return client


async def create_session(
    user: AuthenticatedUser,
    source_language: str | None = None,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
) -> str:
    # user_id is set explicitly here (redundant with the sessions.user_id
    # column's `default auth.uid()`) so the write is self-documenting and so
    # a caller passing an access_token/user mismatch fails fast against the
    # "owner insert" RLS policy instead of silently trusting the caller.
    client = await client_for(user.access_token)
    try:
        result = (
            await client.table("sessions")
            .insert(
                {
                    "user_id": user.id,
                    "source_language": source_language,
                    "target_language": target_language,
                }
            )
            .execute()
        )
        return result.data[0]["id"]
    finally:
        await client.postgrest.aclose()


async def save_message(
    user: AuthenticatedUser,
    session_id: str,
    sequence: int,
    original_text: str,
    translated_text: str | None = None,
    target_language: str | None = None,
) -> None:
    client = await client_for(user.access_token)
    try:
        await client.table("messages").insert(
            {
                "session_id": session_id,
                "sequence": sequence,
                "original_text": original_text,
                "translated_text": translated_text,
                "target_language": target_language,
            }
        ).execute()
    finally:
        await client.postgrest.aclose()


async def update_session_target_language(
    user: AuthenticatedUser, session_id: str, target_language: str
) -> None:
    client = await client_for(user.access_token)
    try:
        await client.table("sessions").update({"target_language": target_language}).eq(
            "id", session_id
        ).execute()
    finally:
        await client.postgrest.aclose()


async def end_session(user: AuthenticatedUser, session_id: str) -> None:
    client = await client_for(user.access_token)
    try:
        # "now" (no parens) is Postgres' special date/time value, resolved by
        # the server at write time - avoids clock skew with this process.
        await client.table("sessions").update({"ended_at": "now"}).eq("id", session_id).execute()
    finally:
        await client.postgrest.aclose()
