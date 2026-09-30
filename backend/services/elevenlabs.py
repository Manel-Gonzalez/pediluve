import base64
import json
import logging
import os
from collections.abc import AsyncIterator

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)

REALTIME_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
TTS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"


class RealtimeTranscriptionSession:
    def __init__(self) -> None:
        self._connection: ClientConnection | None = None

    async def connect(self, audio_format: str = "pcm_16000") -> None:
        api_key = os.environ["ELEVENLABS_API_KEY"]
        url = (
            f"{REALTIME_URL}?model_id=scribe_v2_realtime"
            f"&audio_format={audio_format}&commit_strategy=vad"
        )
        self._connection = await websockets.connect(
            url, additional_headers={"xi-api-key": api_key}
        )

    async def send_audio(self, pcm_bytes: bytes) -> None:
        if self._connection is None:
            return
        message = {
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(pcm_bytes).decode("ascii"),
        }
        await self._connection.send(json.dumps(message))

    async def events(self) -> AsyncIterator[dict]:
        if self._connection is None:
            return
        try:
            async for raw in self._connection:
                yield json.loads(raw)
        except websockets.exceptions.ConnectionClosed:
            return

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None


_tts_client: httpx.AsyncClient | None = None


def _get_tts_client() -> httpx.AsyncClient:
    global _tts_client
    if _tts_client is None:
        _tts_client = httpx.AsyncClient(timeout=30.0)
    return _tts_client


async def synthesize(text: str) -> bytes:
    # One fixed voice for v1 (CLAUDE.md) - no per-language voice mapping, no
    # voice_id parameter here. Callers (services/tts_cache.py) never call
    # this more than once per (message, language): the cache is the whole
    # point, since this is a paid call per invocation.
    api_key = os.environ["ELEVENLABS_API_KEY"].strip()
    voice_id = os.environ["ELEVENLABS_VOICE_ID"].strip()
    if not voice_id:
        raise RuntimeError("ELEVENLABS_VOICE_ID is not set - see .env.example")

    client = _get_tts_client()
    response = await client.post(
        f"{TTS_API_URL}/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_multilingual_v2"},
    )
    if response.status_code >= 400:
        # raise_for_status()'s own exception message doesn't include the
        # response body - ElevenLabs' error responses are JSON explaining
        # *why* (insufficient quota vs. a voice/model not available on this
        # plan vs. something else entirely), which is otherwise invisible.
        logger.error("ElevenLabs TTS request failed (%s): %s", response.status_code, response.text)
    response.raise_for_status()
    return response.content
