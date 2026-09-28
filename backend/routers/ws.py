import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from models.messages import AudioChunkReceived, ClientMessage, EchoMessage, ErrorMessage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await _handle_audio_chunk(websocket, message["bytes"])
            elif message.get("text") is not None:
                await _handle_text_message(websocket, message["text"])
    except WebSocketDisconnect:
        logger.info("Client disconnected")


async def _handle_text_message(websocket: WebSocket, raw: str) -> None:
    try:
        data = json.loads(raw)
        message = ClientMessage.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        await websocket.send_json(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
        return

    echo = EchoMessage(text=message.text)
    await websocket.send_json(echo.model_dump())


async def _handle_audio_chunk(websocket: WebSocket, data: bytes) -> None:
    logger.info("Received audio chunk: %d bytes", len(data))
    await websocket.send_json(AudioChunkReceived(bytes=len(data)).model_dump())
