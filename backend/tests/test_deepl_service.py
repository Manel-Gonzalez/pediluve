import httpx
import pytest

from services import deepl


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, response_json=None, status_code=200):
        self.response_json = response_json or {"translations": [{"text": "hola"}]}
        self.status_code = status_code
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        return httpx.Response(self.status_code, json=self.response_json, request=request)


def _patch_transport(monkeypatch, transport):
    real_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    # translate() caches a module-level client (see deepl._get_client) - reset it
    # so each test starts from a clean, freshly-faked client instead of reusing
    # whatever a previous test cached.
    monkeypatch.setattr(deepl, "_client", None)
    monkeypatch.setattr(deepl.httpx, "AsyncClient", fake_async_client)
    monkeypatch.setenv("DEEPL_API_KEY", "test-key:fx")


@pytest.fixture
def fake_transport(monkeypatch):
    transport = FakeTransport()
    _patch_transport(monkeypatch, transport)
    return transport


async def test_translate_returns_the_translated_text(fake_transport):
    result = await deepl.translate("hello", "es")
    assert result == "hola"


async def test_translate_maps_ui_language_codes_to_deepl_codes(fake_transport):
    await deepl.translate("hello", "en")
    sent = fake_transport.requests[0]
    assert b"target_lang=EN-US" in sent.content


async def test_translate_sends_the_text_to_translate(fake_transport):
    await deepl.translate("hello world", "es")
    sent = fake_transport.requests[0]
    assert b"text=hello+world" in sent.content


async def test_translate_sends_the_api_key_as_an_auth_header(fake_transport):
    await deepl.translate("hello", "es")
    sent = fake_transport.requests[0]
    assert sent.headers["authorization"] == "DeepL-Auth-Key test-key:fx"


async def test_translate_raises_on_a_deepl_error_response(monkeypatch):
    transport = FakeTransport(status_code=456, response_json={"message": "Quota exceeded"})
    _patch_transport(monkeypatch, transport)

    with pytest.raises(httpx.HTTPStatusError):
        await deepl.translate("hello", "es")


async def test_get_client_reuses_the_same_instance_across_calls(monkeypatch):
    monkeypatch.setattr(deepl, "_client", None)
    first = deepl._get_client()
    second = deepl._get_client()
    assert first is second


async def test_translate_reuses_the_client_across_calls(fake_transport):
    await deepl.translate("hello", "es")
    await deepl.translate("hello again", "es")
    assert deepl._get_client() is deepl._get_client()
