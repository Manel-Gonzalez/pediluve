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


@pytest.mark.parametrize("code, deepl_code", [("ro", b"RO"), ("nl", b"NL")])
async def test_romanian_and_dutch_are_supported_targets(fake_transport, code, deepl_code):
    assert code in deepl.SUPPORTED_TARGET_LANGUAGES
    await deepl.translate("hello", code)
    assert b"target_lang=" + deepl_code in fake_transport.requests[0].content


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


async def test_translate_strips_whitespace_from_the_api_key(monkeypatch):
    transport = FakeTransport()
    _patch_transport(monkeypatch, transport)
    # A trailing newline/space from a copy-pasted .env value is a common mistake
    # (see docs/decisions.md) - it must not end up inside the header value.
    monkeypatch.setenv("DEEPL_API_KEY", "test-key:fx\n")

    await deepl.translate("hello", "es")

    sent = transport.requests[0]
    assert sent.headers["authorization"] == "DeepL-Auth-Key test-key:fx"


async def test_translate_raises_a_clear_error_when_the_api_key_is_empty(monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "   ")

    with pytest.raises(RuntimeError, match="DEEPL_API_KEY"):
        await deepl.translate("hello", "es")


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


# ── translate_many ────────────────────────────────────────────────────────


async def test_translate_many_returns_translations_in_order(fake_transport):
    fake_transport.response_json = {"translations": [{"text": "hola"}, {"text": "mundo"}]}

    result = await deepl.translate_many(["hello", "world"], "es")

    assert result == ["hola", "mundo"]
    assert len(fake_transport.requests) == 1


async def test_translate_many_sends_up_to_50_texts_in_one_request(fake_transport):
    texts = [f"text-{i}" for i in range(50)]
    fake_transport.response_json = {"translations": [{"text": t} for t in texts]}

    await deepl.translate_many(texts, "es")

    assert len(fake_transport.requests) == 1
    assert fake_transport.requests[0].content.count(b"text=") == 50


async def test_translate_many_chunks_requests_over_50_texts(monkeypatch):
    texts = [f"text-{i}" for i in range(120)]

    class ChunkingTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.requests: list[httpx.Request] = []

        async def handle_async_request(self, request):
            self.requests.append(request)
            count = request.content.count(b"text=")
            translations = [{"text": f"t{i}"} for i in range(count)]
            return httpx.Response(200, json={"translations": translations}, request=request)

    transport = ChunkingTransport()
    _patch_transport(monkeypatch, transport)

    result = await deepl.translate_many(texts, "es")

    assert [request.content.count(b"text=") for request in transport.requests] == [50, 50, 20]
    assert len(result) == 120


async def test_translate_many_maps_a_failed_chunk_to_nones(monkeypatch):
    texts = [f"text-{i}" for i in range(60)]

    class FailingSecondChunkTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.requests: list[httpx.Request] = []

        async def handle_async_request(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                count = request.content.count(b"text=")
                translations = [{"text": f"ok-{i}"} for i in range(count)]
                return httpx.Response(200, json={"translations": translations}, request=request)
            return httpx.Response(456, json={"message": "Quota exceeded"}, request=request)

    transport = FailingSecondChunkTransport()
    _patch_transport(monkeypatch, transport)

    result = await deepl.translate_many(texts, "es")

    assert result[:50] == [f"ok-{i}" for i in range(50)]
    assert result[50:] == [None] * 10


async def test_translate_many_with_no_texts_returns_an_empty_list_and_does_not_call_deepl(fake_transport):
    result = await deepl.translate_many([], "es")

    assert result == []
    assert fake_transport.requests == []


async def test_translate_many_reuses_the_ui_language_code_mapping(fake_transport):
    fake_transport.response_json = {"translations": [{"text": "hi"}]}

    await deepl.translate_many(["hello"], "en")

    sent = fake_transport.requests[0]
    assert b"target_lang=EN-US" in sent.content
