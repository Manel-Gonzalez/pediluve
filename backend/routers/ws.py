import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from models.messages import (
    ClientMessage,
    EchoMessage,
    ErrorMessage,
    PartialTranscript,
    SetTargetLanguage,
    StartTranscription,
    Transcript,
)
from services import deepl, supabase
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
        self.source_language: str | None = None
        self.target_language: str | None = None
        self.transcript_queue: asyncio.Queue[str] | None = None
        self.transcript_worker_task: asyncio.Task | None = None
        self._background_tasks: set[asyncio.Task] = set()

    async def send(self, payload: dict) -> None:
        async with self.send_lock:
            await self.websocket.send_json(payload)

    def _spawn_background(self, coro) -> None:
        # Tracked so the task isn't garbage-collected mid-flight, and so
        # _stop_transcription can wait for it before ending the DB session.
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

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

        if msg_type == "set_target_language":
            try:
                request = SetTargetLanguage.model_validate(data)
            except ValidationError as exc:
                await self.send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
                return
            if request.target_language not in deepl.SUPPORTED_TARGET_LANGUAGES:
                await self.send(
                    ErrorMessage(
                        message=f"Unsupported target language: {request.target_language}"
                    ).model_dump()
                )
                return
            self.target_language = request.target_language
            if self.db_session_id is not None:
                # Fire-and-forget: this is a network write, and the main receive
                # loop must keep reading audio/messages off the socket without
                # stalling on it (same reasoning as queuing committed transcripts).
                self._spawn_background(
                    self._persist_target_language(self.db_session_id, self.target_language)
                )
            return

        await self.send(ErrorMessage(message=f"Unknown message type: {msg_type}").model_dump())

    async def _start_transcription(self, data: dict) -> None:
        if self.stt_session is not None:
            return

        try:
            request = StartTranscription.model_validate(data)
        except ValidationError as exc:
            await self.send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
            return

        # Captured for display/persistence (KAN-6) and a future Phase-3 re-translation
        # use. Not yet passed to RealtimeTranscriptionSession.connect(): whether
        # scribe_v2_realtime even accepts a language hint is unconfirmed (see
        # docs/decisions.md) - not something to guess at on an external API.
        self.source_language = request.source_language
        session = RealtimeTranscriptionSession()
        try:
            await session.connect(audio_format=request.audio_format)
        except Exception as exc:
            await self.send(ErrorMessage(message=f"Could not start transcription: {exc}").model_dump())
            return

        self.stt_session = session
        self.sequence = 0
        try:
            self.db_session_id = await supabase.create_session(
                source_language=self.source_language,
                target_language=self.target_language or supabase.DEFAULT_TARGET_LANGUAGE,
            )
        except Exception:
            logger.exception("Could not create Supabase session")
            self.db_session_id = None

        # Committed transcripts are queued rather than awaited inline here, so a
        # slow (or slow-to-fail) DeepL call can't stall relaying the next partial/
        # committed event off the ElevenLabs connection. A single worker drains the
        # queue in order, which keeps sequence numbers and message order correct.
        self.transcript_queue = asyncio.Queue()
        self.relay_task = asyncio.create_task(self._relay_transcripts(session))
        self.transcript_worker_task = asyncio.create_task(self._process_transcript_queue())

    async def _stop_transcription(self) -> None:
        if self.stt_session is not None:
            await self.stt_session.close()
        if self.relay_task is not None:
            await self.relay_task
        if self.transcript_queue is not None:
            await self.transcript_queue.join()
        if self.transcript_worker_task is not None:
            self.transcript_worker_task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        await self._end_db_session()
        self.stt_session = None
        self.relay_task = None
        self.transcript_queue = None
        self.transcript_worker_task = None

    async def _relay_transcripts(self, session: RealtimeTranscriptionSession) -> None:
        async for event in session.events():
            event_type = event.get("message_type")
            if event_type == "partial_transcript":
                await self.send(PartialTranscript(text=event["text"]).model_dump())
            elif event_type == "committed_transcript":
                await self.transcript_queue.put(event["text"])
            elif event_type in ("session_started", "warning", "edited_transcript"):
                logger.info("ElevenLabs event: %s", event)
            elif "error" in event:
                await self.send(ErrorMessage(message=str(event["error"])).model_dump())
            else:
                logger.warning("Unhandled ElevenLabs event: %s", event)

    async def _process_transcript_queue(self) -> None:
        while True:
            text = await self.transcript_queue.get()
            try:
                await self._handle_committed_transcript(text)
            finally:
                self.transcript_queue.task_done()

    async def _handle_committed_transcript(self, text: str) -> None:
        # Captured before the DeepL await, not re-read after it resolves: a
        # set_target_language arriving while this translation is in flight must not
        # reassign it to the wrong language.
        target_language = self.target_language
        translated_text: str | None = None
        if target_language is not None:
            try:
                translated_text = await deepl.translate(text, target_language)
            except Exception:
                logger.exception("Could not translate transcript")

        await self.send(
            Transcript(
                original_text=text,
                translated_text=translated_text,
                target_language=target_language,
            ).model_dump()
        )
        if self.db_session_id is None:
            return
        try:
            await supabase.save_message(
                self.db_session_id,
                self.sequence,
                text,
                translated_text=translated_text,
                target_language=target_language,
            )
            self.sequence += 1
        except Exception:
            logger.exception("Could not save message to Supabase")

    async def _persist_target_language(self, session_id: str, target_language: str) -> None:
        try:
            await supabase.update_session_target_language(session_id, target_language)
        except Exception:
            logger.exception("Could not update session target language")

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
        if self.transcript_worker_task is not None:
            self.transcript_worker_task.cancel()
        await self._end_db_session()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ConnectionHandler(websocket).run()
