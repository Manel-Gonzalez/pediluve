import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from models.messages import ClientMessage, EchoMessage, ErrorMessage, PartialTranscript, Transcript
from services import supabase
from services.elevenlabs import RealtimeTranscriptionSession

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionHandler:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.send_lock = asyncio.Lock()
        self.stt_session: RealtimeTranscriptionSession | None = None
        self.relay_task: asyncio.Task | None = None
        self.db_session_id: str | None = None
        self.sequence = 0

    async def send(self, payload: dict) -> None:
        async with self.send_lock:
            await self.websocket.send_json(payload)

    async def run(self) -> None:
        await self.websocket.accept()
        try:
            while True:
                message = await self.websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break

                if message.get("bytes") is not None:
                    if self.stt_session is not None:
                        await self.stt_session.send_audio(message["bytes"])
                    continue

                if message.get("text") is None:
                    continue

                await self._handle_text_message(message["text"])
        except WebSocketDisconnect:
            logger.info("Client disconnected")
        finally:
            await self._cleanup()

    async def _handle_text_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            await self.send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
            return

        msg_type = data.get("type")

        if msg_type == "message":
            try:
                echo_request = ClientMessage.model_validate(data)
            except ValidationError as exc:
                await self.send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
                return
            await self.send(EchoMessage(text=echo_request.text).model_dump())
            return

        if msg_type == "start_transcription":
            await self._start_transcription(data)
            return

        if msg_type == "stop_transcription":
            await self._stop_transcription()
            return

        await self.send(ErrorMessage(message=f"Unknown message type: {msg_type}").model_dump())

    async def _start_transcription(self, data: dict) -> None:
        if self.stt_session is not None:
            return

        audio_format = data.get("audio_format", "pcm_16000")
        session = RealtimeTranscriptionSession()
        try:
            await session.connect(audio_format=audio_format)
        except Exception as exc:
            await self.send(ErrorMessage(message=f"Could not start transcription: {exc}").model_dump())
            return

        self.stt_session = session
        self.sequence = 0
        try:
            self.db_session_id = await supabase.create_session()
        except Exception:
            logger.exception("Could not create Supabase session")
            self.db_session_id = None

        self.relay_task = asyncio.create_task(self._relay_transcripts(session))

    async def _stop_transcription(self) -> None:
        if self.stt_session is not None:
            await self.stt_session.close()
        if self.relay_task is not None:
            await self.relay_task
        await self._end_db_session()
        self.stt_session = None
        self.relay_task = None

    async def _relay_transcripts(self, session: RealtimeTranscriptionSession) -> None:
        async for event in session.events():
            event_type = event.get("message_type")
            if event_type == "partial_transcript":
                await self.send(PartialTranscript(text=event["text"]).model_dump())
            elif event_type == "committed_transcript":
                await self._handle_committed_transcript(event["text"])
            elif event_type in ("session_started", "warning", "edited_transcript"):
                logger.info("ElevenLabs event: %s", event)
            elif "error" in event:
                await self.send(ErrorMessage(message=str(event["error"])).model_dump())
            else:
                logger.warning("Unhandled ElevenLabs event: %s", event)

    async def _handle_committed_transcript(self, text: str) -> None:
        await self.send(Transcript(text=text).model_dump())
        if self.db_session_id is None:
            return
        try:
            await supabase.save_message(self.db_session_id, self.sequence, text)
            self.sequence += 1
        except Exception:
            logger.exception("Could not save message to Supabase")

    async def _end_db_session(self) -> None:
        if self.db_session_id is None:
            return
        try:
            await supabase.end_session(self.db_session_id)
        except Exception:
            logger.exception("Could not end Supabase session")
        self.db_session_id = None

    async def _cleanup(self) -> None:
        if self.stt_session is not None:
            await self.stt_session.close()
        if self.relay_task is not None:
            self.relay_task.cancel()
        await self._end_db_session()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ConnectionHandler(websocket).run()
