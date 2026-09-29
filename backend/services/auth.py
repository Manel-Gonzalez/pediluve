import os
from dataclasses import dataclass

from supabase import AsyncClient, create_async_client
from supabase_auth.errors import AuthApiError


@dataclass
class AuthenticatedUser:
    id: str
    email: str | None
    access_token: str


class AuthError(Exception):
    """The token itself is invalid, malformed, or expired."""


class AuthServiceUnavailable(Exception):
    """verify_access_token couldn't reach Supabase Auth to check the token -
    not the same as the token being bad, and callers should not treat it as
    a 401 (see routers/me.py)."""


_client: AsyncClient | None = None


async def _get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await create_async_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _client


async def verify_access_token(access_token: str) -> AuthenticatedUser:
    # .strip(): same failure mode as the DeepL key fix - a trailing
    # newline/space from a copy-pasted token should not silently fail deep
    # inside the auth client instead of with a clear error here.
    access_token = access_token.strip()
    if not access_token:
        raise AuthError("Access token is empty")

    client = await _get_client()
    try:
        response = await client.auth.get_user(access_token)
    except AuthApiError as exc:
        # The auth server responded and said the token is bad (expired,
        # malformed, revoked) - a real 401, not an outage.
        raise AuthError("Invalid or expired access token") from exc
    except Exception as exc:
        raise AuthServiceUnavailable(f"Could not reach Supabase Auth: {exc}") from exc

    if response is None or response.user is None:
        raise AuthError("Invalid or expired access token")

    return AuthenticatedUser(id=response.user.id, email=response.user.email, access_token=access_token)
