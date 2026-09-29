import pytest
from supabase_auth.errors import AuthApiError

from services import auth


class FakeUser:
    def __init__(self, id, email):
        self.id = id
        self.email = email


class FakeUserResponse:
    def __init__(self, user):
        self.user = user


class FakeAuth:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.received_tokens = []

    async def get_user(self, token):
        self.received_tokens.append(token)
        if self._exc is not None:
            raise self._exc
        return self._response


class FakeClient:
    def __init__(self, auth_obj):
        self.auth = auth_obj


@pytest.fixture
def fake_client(monkeypatch):
    def make(auth_obj):
        client = FakeClient(auth_obj)

        async def fake_get_client():
            return client

        monkeypatch.setattr(auth, "_get_client", fake_get_client)
        return client

    return make


async def test_verify_access_token_returns_the_authenticated_user(fake_client):
    fake_auth = FakeAuth(response=FakeUserResponse(FakeUser("user-1", "a@example.com")))
    fake_client(fake_auth)

    result = await auth.verify_access_token("a-token")

    assert result.id == "user-1"
    assert result.email == "a@example.com"
    assert result.access_token == "a-token"


async def test_verify_access_token_strips_whitespace(fake_client):
    fake_auth = FakeAuth(response=FakeUserResponse(FakeUser("user-1", "a@example.com")))
    fake_client(fake_auth)

    result = await auth.verify_access_token("  a-token  \n")

    assert result.access_token == "a-token"
    assert fake_auth.received_tokens == ["a-token"]


async def test_verify_access_token_raises_on_empty_token(fake_client):
    fake_auth = FakeAuth()
    fake_client(fake_auth)

    with pytest.raises(auth.AuthError):
        await auth.verify_access_token("   ")

    assert fake_auth.received_tokens == []


async def test_verify_access_token_raises_when_no_user_is_returned(fake_client):
    fake_auth = FakeAuth(response=FakeUserResponse(None))
    fake_client(fake_auth)

    with pytest.raises(auth.AuthError):
        await auth.verify_access_token("a-token")


async def test_verify_access_token_raises_auth_error_when_the_server_rejects_the_token(fake_client):
    fake_auth = FakeAuth(exc=AuthApiError("expired", status=401, code=None))
    fake_client(fake_auth)

    with pytest.raises(auth.AuthError):
        await auth.verify_access_token("a-token")


async def test_verify_access_token_raises_service_unavailable_on_an_unexpected_error(fake_client):
    fake_auth = FakeAuth(exc=RuntimeError("connection refused"))
    fake_client(fake_auth)

    with pytest.raises(auth.AuthServiceUnavailable):
        await auth.verify_access_token("a-token")
