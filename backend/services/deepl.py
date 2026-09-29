import logging
import os

import httpx

logger = logging.getLogger(__name__)

DEEPL_API_URL = "https://api-free.deepl.com/v2/translate"

# DeepL accepts multiple `text` fields in one request; chunking above this
# keeps each request a reasonable size rather than assuming DeepL's own limit
# (unverified from this sandboxed environment - see docs/decisions.md).
_MAX_BATCH_SIZE = 50

# Maps the UI's lowercase language codes (CLAUDE.md's candidate set) to the exact
# target_lang values DeepL's API expects. DeepL rejects bare "EN" as a target, so
# it's mapped to "EN-US". "CA" (Catalan) is unverified against DeepL's live
# /v2/languages list - network to api-free.deepl.com is blocked from this sandbox.
# If DeepL rejects it, translate() raises and the caller already treats that as a
# per-message translation failure (logged, translated_text stays null) rather than
# a crash - see docs/decisions.md.
_TARGET_LANGUAGE_CODES = {
    "es": "ES",
    "ca": "CA",
    "en": "EN-US",
    "fr": "FR",
    "de": "DE",
}

# The UI-facing codes callers (routers/ws.py) may accept from a client. Kept as a
# public name derived from the mapping above so there is one source of truth.
SUPPORTED_TARGET_LANGUAGES = frozenset(_TARGET_LANGUAGE_CODES)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def translate(text: str, target_language: str) -> str:
    deepl_code = _TARGET_LANGUAGE_CODES.get(target_language, target_language.upper())
    # .strip(): a trailing newline/space from a copy-pasted .env value turns into
    # an invalid HTTP header and fails as a confusing httpx.LocalProtocolError
    # deep in the request internals rather than this clear message.
    api_key = os.environ["DEEPL_API_KEY"].strip()
    if not api_key:
        raise RuntimeError("DEEPL_API_KEY is set but empty - check backend/.env")
    client = _get_client()
    response = await client.post(
        DEEPL_API_URL,
        headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
        data={"text": text, "target_lang": deepl_code},
    )
    response.raise_for_status()
    return response.json()["translations"][0]["text"]


async def translate_many(texts: list[str], target_language: str) -> list[str | None]:
    # For an on-demand re-translation view (KAN-25): a failed chunk must not
    # take down the whole view, so it maps to None for each of its texts
    # (the caller shows "translation unavailable") rather than raising.
    if not texts:
        return []

    deepl_code = _TARGET_LANGUAGE_CODES.get(target_language, target_language.upper())
    api_key = os.environ["DEEPL_API_KEY"].strip()
    if not api_key:
        raise RuntimeError("DEEPL_API_KEY is set but empty - check backend/.env")
    client = _get_client()

    results: list[str | None] = []
    for start in range(0, len(texts), _MAX_BATCH_SIZE):
        chunk = texts[start : start + _MAX_BATCH_SIZE]
        try:
            response = await client.post(
                DEEPL_API_URL,
                headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
                # httpx form-encodes a list value as repeated fields (text=a&text=b&...),
                # which is how DeepL accepts multiple texts in one request.
                data={"text": chunk, "target_lang": deepl_code},
            )
            response.raise_for_status()
            translations = response.json()["translations"]
            results.extend(translation["text"] for translation in translations)
        except Exception:
            logger.exception("Could not translate a batch of %d text(s)", len(chunk))
            results.extend([None] * len(chunk))

    return results
