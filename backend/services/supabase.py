import os

from supabase import AsyncClient, create_async_client

from services.auth import AuthenticatedUser


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
    title: str,
    source_language: str | None = None,
    target_language: str | None = None,
) -> dict:
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
                    "title": title,
                    "source_language": source_language,
                    "target_language": target_language,
                }
            )
            .execute()
        )
        row = result.data[0]
        row["role"] = "owner"
        row["guest_language"] = None
        return row
    finally:
        await client.postgrest.aclose()


async def _attach_role_and_guest_language(client: AsyncClient, user: AuthenticatedUser, rows: list[dict]) -> None:
    # Mutates rows in place. A session visible under RLS is either owned
    # (sessions.user_id = auth.uid()) or guest-visible (a session_guests row
    # for this user, KAN-59) - never both, so which query matched tells us
    # which role applies. A separate query rather than a PostgREST embed,
    # same reasoning as list_sessions' own message-count query below: two
    # simple queries beat one uncertain one.
    if not rows:
        return
    ids = [row["id"] for row in rows]
    guests_result = (
        await client.table("session_guests")
        .select("session_id, target_language")
        .eq("user_id", user.id)
        .in_("session_id", ids)
        .execute()
    )
    guest_languages = {row["session_id"]: row["target_language"] for row in guests_result.data}
    for row in rows:
        # Ownership checked first: nothing stops an owner from also holding
        # a session_guests row for their own session (e.g. scanning their
        # own QR code while signed in), and owner must win if so - it's the
        # stronger relationship, and the one that actually governs what
        # they can do (rename/delete/etc. stay owner-only regardless).
        if row["user_id"] == user.id:
            row["role"] = "owner"
            row["guest_language"] = None
        elif row["id"] in guest_languages:
            row["role"] = "guest"
            row["guest_language"] = guest_languages[row["id"]]
        else:
            row["role"] = "owner"
            row["guest_language"] = None


async def save_message(
    user: AuthenticatedUser,
    session_id: str,
    sequence: int,
    original_text: str,
    translated_text: str | None = None,
    target_language: str | None = None,
) -> dict:
    # Returns the inserted row (not just None) so callers can thread its id
    # through to the live room (KAN-58's request_audio needs a stable
    # message_id to key the TTS cache on).
    client = await client_for(user.access_token)
    try:
        result = (
            await client.table("messages")
            .insert(
                {
                    "session_id": session_id,
                    "sequence": sequence,
                    "original_text": original_text,
                    "translated_text": translated_text,
                    "target_language": target_language,
                }
            )
            .execute()
        )
        return result.data[0]
    finally:
        await client.postgrest.aclose()


async def get_message_audio(user: AuthenticatedUser, message_id: str, language: str) -> dict | None:
    client = await client_for(user.access_token)
    try:
        result = (
            await client.table("message_audio")
            .select("*")
            .eq("message_id", message_id)
            .eq("language", language)
            .execute()
        )
        return result.data[0] if result.data else None
    finally:
        await client.postgrest.aclose()


async def create_message_audio(
    user: AuthenticatedUser, message_id: str, language: str, storage_path: str
) -> dict:
    client = await client_for(user.access_token)
    try:
        result = (
            await client.table("message_audio")
            .insert({"message_id": message_id, "language": language, "storage_path": storage_path})
            .execute()
        )
        return result.data[0]
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


async def update_session_source_language(
    user: AuthenticatedUser, session_id: str, source_language: str
) -> None:
    client = await client_for(user.access_token)
    try:
        await client.table("sessions").update({"source_language": source_language}).eq(
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


async def list_sessions(
    user: AuthenticatedUser, limit: int = 20, offset: int = 0
) -> tuple[list[dict], bool]:
    client = await client_for(user.access_token)
    try:
        result = (
            await client.table("sessions")
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + limit)
            .execute()
        )
        # Fetch one row past the page to know if there's more, without a
        # separate count query.
        has_more = len(result.data) > limit
        rows = result.data[:limit]

        if rows:
            ids = [row["id"] for row in rows]
            # A separate query rather than a nested embed/count - PostgREST's
            # embedded-count syntax behavior isn't verified from here, so two
            # simple queries beat one uncertain one.
            messages_result = (
                await client.table("messages").select("session_id").in_("session_id", ids).execute()
            )
            counts: dict[str, int] = {}
            for message in messages_result.data:
                counts[message["session_id"]] = counts.get(message["session_id"], 0) + 1
            for row in rows:
                row["message_count"] = counts.get(row["id"], 0)
            await _attach_role_and_guest_language(client, user, rows)

        return rows, has_more
    finally:
        await client.postgrest.aclose()


async def get_session_with_messages(user: AuthenticatedUser, session_id: str) -> dict | None:
    client = await client_for(user.access_token)
    try:
        session_result = await client.table("sessions").select("*").eq("id", session_id).execute()
        if not session_result.data:
            return None
        row = session_result.data[0]
        await _attach_role_and_guest_language(client, user, [row])

        messages_result = (
            await client.table("messages")
            .select("*")
            .eq("session_id", session_id)
            .order("sequence")
            .execute()
        )
        row["messages"] = messages_result.data
        return row
    finally:
        await client.postgrest.aclose()


async def get_session_by_share_token(user: AuthenticatedUser, share_token: str) -> dict | None:
    # Used right after add_session_guest (KAN-60) to return the
    # newly-accessible session's summary - RLS only makes the row visible
    # once the guest row actually exists, so this must run after that RPC,
    # not before.
    client = await client_for(user.access_token)
    try:
        result = await client.table("sessions").select("*").eq("share_token", share_token).execute()
        if not result.data:
            return None
        row = result.data[0]
        await _attach_role_and_guest_language(client, user, [row])

        messages_result = (
            await client.table("messages").select("session_id").eq("session_id", row["id"]).execute()
        )
        row["message_count"] = len(messages_result.data)
        return row
    finally:
        await client.postgrest.aclose()


async def add_session_guest(user: AuthenticatedUser, share_token: str, target_language: str | None) -> None:
    client = await client_for(user.access_token)
    try:
        await client.rpc(
            "add_session_guest", {"share_token": share_token, "target_language": target_language}
        ).execute()
    finally:
        await client.postgrest.aclose()


async def remove_session_guest(user: AuthenticatedUser, session_id: str) -> bool:
    client = await client_for(user.access_token)
    try:
        result = (
            await client.table("session_guests")
            .delete()
            .eq("session_id", session_id)
            .eq("user_id", user.id)
            .execute()
        )
        return bool(result.data)
    finally:
        await client.postgrest.aclose()


async def rename_session(user: AuthenticatedUser, session_id: str, title: str) -> dict | None:
    client = await client_for(user.access_token)
    try:
        result = await client.table("sessions").update({"title": title}).eq("id", session_id).execute()
        if not result.data:
            return None
        # Rename's own RLS policy is owner-only (003_auth_and_rls.sql) - a
        # guest's update simply matches zero rows and falls into the branch
        # above, so reaching here always means role="owner".
        row = result.data[0]
        row["role"] = "owner"
        row["guest_language"] = None
        return row
    finally:
        await client.postgrest.aclose()


async def delete_session(user: AuthenticatedUser, session_id: str) -> bool:
    client = await client_for(user.access_token)
    try:
        result = await client.table("sessions").delete().eq("id", session_id).execute()
        return bool(result.data)
    finally:
        await client.postgrest.aclose()
