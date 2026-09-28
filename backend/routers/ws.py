import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from models.messages import ClientMessage, EchoMessage, ErrorMessage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            await _handle_message(websocket, raw)
    except WebSocketDisconnect:
        logger.info("Client disconnected")


async def _handle_message(websocket: WebSocket, raw: str) -> None:
    try:
        data = json.loads(raw)
        message = ClientMessage.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        await websocket.send_json(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
        return

    echo = EchoMessage(text=message.text)
    await websocket.send_json(echo.model_dump())
