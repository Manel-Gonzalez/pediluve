import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from models.messages import ClientMessage, EchoMessage, ErrorMessage, PartialTranscript, Transcript
from services.elevenlabs import RealtimeTranscriptionSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    send_lock = asyncio.Lock()
    session: RealtimeTranscriptionSession | None = None
    relay_task: asyncio.Task | None = None

    async def send(payload: dict) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                if session is not None:
                    await session.send_audio(message["bytes"])
                continue

            if message.get("text") is None:
                continue

            session, relay_task = await _handle_text_message(
                message["text"], send, session, relay_task
            )
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        if session is not None:
            await session.close()
        if relay_task is not None:
            relay_task.cancel()


async def _handle_text_message(
    raw: str,
    send,
    session: RealtimeTranscriptionSession | None,
    relay_task: asyncio.Task | None,
) -> tuple[RealtimeTranscriptionSession | None, asyncio.Task | None]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        await send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
        return session, relay_task

    msg_type = data.get("type")

    if msg_type == "message":
        try:
            echo_request = ClientMessage.model_validate(data)
        except ValidationError as exc:
            await send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
            return session, relay_task
        await send(EchoMessage(text=echo_request.text).model_dump())
        return session, relay_task

    if msg_type == "start_transcription":
        if session is not None:
            return session, relay_task
        audio_format = data.get("audio_format", "pcm_16000")
        new_session = RealtimeTranscriptionSession()
        try:
            await new_session.connect(audio_format=audio_format)
        except Exception as exc:
            await send(ErrorMessage(message=f"Could not start transcription: {exc}").model_dump())
            return session, relay_task
        task = asyncio.create_task(_relay_transcripts(new_session, send))
        return new_session, task

    if msg_type == "stop_transcription":
        if session is not None:
            await session.close()
        if relay_task is not None:
            await relay_task
        return None, None

    await send(ErrorMessage(message=f"Unknown message type: {msg_type}").model_dump())
    return session, relay_task


async def _relay_transcripts(session: RealtimeTranscriptionSession, send) -> None:
    async for event in session.events():
        event_type = event.get("message_type")
        if event_type == "partial_transcript":
            await send(PartialTranscript(text=event["text"]).model_dump())
        elif event_type == "committed_transcript":
            await send(Transcript(text=event["text"]).model_dump())
        elif event_type in ("session_started", "warning", "edited_transcript"):
            logger.info("ElevenLabs event: %s", event)
        elif "error" in event:
            await send(ErrorMessage(message=str(event["error"])).model_dump())
        else:
            logger.warning("Unhandled ElevenLabs event: %s", event)
