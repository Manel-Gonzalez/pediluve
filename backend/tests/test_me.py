from fastapi.testclient import TestClient

from main import app
from routers.me import get_current_user
from services.auth import AuthenticatedUser

client = TestClient(app)


def test_me_returns_the_current_user():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="user-1", email="a@example.com", access_token="tok"
    )
    try:
        response = client.get("/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"id": "user-1", "email": "a@example.com"}


def test_me_without_authorization_header_is_401():
    response = client.get("/me")
    assert response.status_code == 401


def test_me_with_a_malformed_authorization_header_is_401():
    response = client.get("/me", headers={"Authorization": "Token abc"})
    assert response.status_code == 401


def test_me_with_a_token_that_fails_verification_is_401(monkeypatch):
    from services.auth import AuthError

    async def failing_verify(token):
        raise AuthError("bad token")

    monkeypatch.setattr("routers.me.verify_access_token", failing_verify)
    response = client.get("/me", headers={"Authorization": "Bearer bad"})
    assert response.status_code == 401


def test_me_when_the_auth_service_is_unreachable_is_503(monkeypatch):
    from services.auth import AuthServiceUnavailable

    async def unavailable_verify(token):
        raise AuthServiceUnavailable("connection refused")

    monkeypatch.setattr("routers.me.verify_access_token", unavailable_verify)
    response = client.get("/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 503
