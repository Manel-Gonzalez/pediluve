import base64
import json
import os
from collections.abc import AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection

REALTIME_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"


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


async def synthesize(text: str) -> bytes:
    raise NotImplementedError("TTS wired up in Phase 4")
