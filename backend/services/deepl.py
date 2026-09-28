import os

import httpx

DEEPL_API_URL = "https://api-free.deepl.com/v2/translate"

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


async def translate(text: str, target_language: str) -> str:
    deepl_code = _TARGET_LANGUAGE_CODES.get(target_language, target_language.upper())
    api_key = os.environ["DEEPL_API_KEY"]
    async with httpx.AsyncClient() as client:
        response = await client.post(
            DEEPL_API_URL,
            headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
            data={"text": text, "target_lang": deepl_code},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()["translations"][0]["text"]
