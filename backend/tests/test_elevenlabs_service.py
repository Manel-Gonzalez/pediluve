import httpx
import pytest

from services import elevenlabs


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, content: bytes = b"fake-mp3-bytes", status_code: int = 200):
        self.content = content
        self.status_code = status_code
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        return httpx.Response(self.status_code, content=self.content, request=request)


@pytest.fixture
def fake_transport(monkeypatch):
    transport = FakeTransport()
    real_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    # synthesize() caches a module-level client (see elevenlabs._get_tts_client)
    # - reset it so each test starts from a freshly-faked client.
    monkeypatch.setattr(elevenlabs, "_tts_client", None)
    monkeypatch.setattr(elevenlabs.httpx, "AsyncClient", fake_async_client)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-123")
    return transport


async def test_synthesize_returns_the_audio_bytes(fake_transport):
    result = await elevenlabs.synthesize("hola")
    assert result == b"fake-mp3-bytes"


async def test_synthesize_posts_to_the_configured_voice_id(fake_transport):
    await elevenlabs.synthesize("hola")
    sent = fake_transport.requests[0]
    assert sent.url.path == "/v1/text-to-speech/voice-123"


async def test_synthesize_sends_the_api_key_header(fake_transport):
    await elevenlabs.synthesize("hola")
    sent = fake_transport.requests[0]
    assert sent.headers["xi-api-key"] == "test-key"


async def test_synthesize_sends_the_text_as_json(fake_transport):
    await elevenlabs.synthesize("hola mundo")
    sent = fake_transport.requests[0]
    assert b'"text":"hola mundo"' in sent.content


async def test_synthesize_without_a_voice_id_raises(monkeypatch, fake_transport):
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "")
    with pytest.raises(RuntimeError):
        await elevenlabs.synthesize("hola")


async def test_synthesize_raises_on_an_error_response(monkeypatch):
    transport = FakeTransport(content=b"nope", status_code=401)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(elevenlabs, "_tts_client", None)
    monkeypatch.setattr(
        elevenlabs.httpx, "AsyncClient", lambda *a, **kw: real_async_client(*a, transport=transport, **kw)
    )
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-123")

    with pytest.raises(httpx.HTTPStatusError):
        await elevenlabs.synthesize("hola")
