import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from models.messages import (
    Authenticate,
    Authenticated,
    ClientMessage,
    EchoMessage,
    ErrorMessage,
    PartialTranscript,
    RetranslatedTranscripts,
    SetTargetLanguage,
    StartTranscription,
    Transcript,
)
from services import deepl, supabase
from services.auth import AuthenticatedUser, AuthError, AuthServiceUnavailable, verify_access_token
from services.elevenlabs import RealtimeTranscriptionSession

AUTH_REQUIRED_CLOSE_CODE = 4401
# Distinct from AUTH_REQUIRED_CLOSE_CODE: the token wasn't necessarily bad,
# Supabase Auth just couldn't be reached - a client should retry, not treat
# this like an invalid session and force a re-login (see services/auth.py).
AUTH_SERVICE_UNAVAILABLE_CLOSE_CODE = 4503

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionHandler:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.send_lock = asyncio.Lock()
        self.user: AuthenticatedUser | None = None
        self._closed = False
        self.stt_session: RealtimeTranscriptionSession | None = None
        self.relay_task: asyncio.Task | None = None
        self.db_session_id: str | None = None
        self.sequence = 0
        self.source_language: str | None = None
        self.target_language: str | None = None
        self.transcript_queue: asyncio.Queue[str] | None = None
        self.transcript_worker_task: asyncio.Task | None = None
        self._background_tasks: set[asyncio.Task] = set()
        # Original text of every committed transcript for the life of this
        # connection, in order - lets a later target-language change
        # retranslate everything said so far, not just what's said from then
        # on. Deliberately NOT reset per recording (unlike sequence/
        # db_session_id): the frontend's own transcriptRows keeps accumulating
        # across multiple stop/start cycles in the same connection too (never
        # cleared on a fresh start_transcription), and retranslated_transcripts
        # wholesale-replaces that list - resetting this per recording would
        # silently drop every earlier recording's rows from the screen the
        # next time the language changes.
        self.committed_texts: list[str] = []
        # Bumped on every retranslation-triggering language change; a background
        # retranslation checks it's still current before sending its result, so
        # a fast second change can't be clobbered by a slower first one that
        # finishes later (see _retranslate_committed_texts).
        self._retranslation_generation = 0

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
                    if self.user is None:
                        await self._reject("Authentication required")
                        break
                    if self.stt_session is not None:
                        await self.stt_session.send_audio(message["bytes"])
                    continue

                if message.get("text") is None:
                    continue

                await self._handle_text_message(message["text"])
                if self._closed:
                    break
        except WebSocketDisconnect:
            logger.info("Client disconnected")
        finally:
            await self._cleanup()

    async def _reject(self, message: str, code: int = AUTH_REQUIRED_CLOSE_CODE) -> None:
        # send() (which self.send() also uses) and close() share send_lock so
        # they run as one atomic unit - otherwise a concurrent background send
        # (the transcript worker, the relay task) could interleave between
        # this error message and the close.
        async with self.send_lock:
            await self.websocket.send_json(ErrorMessage(message=message).model_dump())
            await self.websocket.close(code=code)
        self._closed = True

    async def _authenticate(self, data: dict) -> None:
        try:
            request = Authenticate.model_validate(data)
        except ValidationError as exc:
            await self._reject(f"Invalid message: {exc}")
            return

        try:
            authenticated_user = await verify_access_token(request.access_token)
        except AuthError:
            await self._reject("Invalid or expired access token")
            return
        except AuthServiceUnavailable:
            await self._reject(
                "Authentication service unavailable", code=AUTH_SERVICE_UNAVAILABLE_CLOSE_CODE
            )
            return

        if self.user is not None and self.user.id != authenticated_user.id:
            await self._reject("Cannot re-authenticate as a different user")
            return

        # Re-authenticating as the same user (e.g. a refreshed Supabase access
        # token) swaps the stored user in place - later calls read self.user
        # fresh rather than a value captured earlier, so an in-flight
        # save/update picks up the new token if it hasn't reached Supabase yet.
        self.user = authenticated_user
        await self.send(Authenticated(user_id=authenticated_user.id).model_dump())

    async def _handle_text_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            # Unauthenticated + garbage input closes like any other non-
            # "authenticate" first message, instead of leaving an
            # unauthenticated socket open indefinitely for a peer that never
            # sends valid JSON.
            if self.user is None:
                await self._reject(f"Invalid message: {exc}")
            else:
                await self.send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
            return

        msg_type = data.get("type")

        if msg_type == "authenticate":
            await self._authenticate(data)
            return

        if self.user is None:
            await self._reject("Authentication required")
            return

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
            previous_target_language = self.target_language
            self.target_language = request.target_language
            if self.db_session_id is not None:
                # Fire-and-forget: this is a network write, and the main receive
                # loop must keep reading audio/messages off the socket without
                # stalling on it (same reasoning as queuing committed transcripts).
                self._spawn_background(
                    self._persist_target_language(self.db_session_id, self.target_language)
                )
            if self.target_language != previous_target_language and self.committed_texts:
                self._retranslation_generation += 1
                self._spawn_background(
                    self._retranslate_committed_texts(
                        self.target_language, self._retranslation_generation
                    )
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
                self.user,
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
                # ElevenLabs' VAD occasionally commits a segment with no
                # recognized speech (silence, noise) - an empty or
                # whitespace-only text rather than skipping the event
                # entirely. Filtered here, at the source, so it never reaches
                # the client, spends a DeepL call, or clutters Supabase/the
                # in-memory retranslation history with a blank row.
                text = event["text"]
                if text.strip():
                    await self.transcript_queue.put(text)
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
        # Tracked regardless of translation outcome, so a later target-language
        # change has the full transcript to retranslate even if this specific
        # line's own translation failed.
        self.committed_texts.append(text)

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

        if self.db_session_id is not None:
            try:
                # self.user read here, not captured earlier in this method - if a
                # re-authenticate swapped it while the DeepL call above was in
                # flight, this save uses the new token, per KAN-18.
                await supabase.save_message(
                    self.user,
                    self.db_session_id,
                    self.sequence,
                    text,
                    translated_text=translated_text,
                    target_language=target_language,
                )
                self.sequence += 1
            except Exception:
                logger.exception("Could not save message to Supabase")

        # Persisted before sending, not after: on a real disconnect, send()
        # raises WebSocketDisconnect once the socket write actually fails,
        # which must not skip (or, if unguarded, wipe out via an uncaught
        # exception) the save above - the disconnect/cancellation-shielded
        # cleanup path this now runs under exists precisely to still persist
        # a committed transcript the client will never see.
        try:
            await self.send(
                Transcript(
                    original_text=text,
                    translated_text=translated_text,
                    target_language=target_language,
                ).model_dump()
            )
        except WebSocketDisconnect:
            pass

    async def _retranslate_committed_texts(self, target_language: str, generation: int) -> None:
        # Iterates the live list, not a snapshot: retranslated_transcripts
        # wholesale-replaces the frontend's transcript list (no per-row id
        # goes over the wire), so a transcript committed by the normal path
        # while this loop is still running must end up in this result too -
        # otherwise the wholesale replace would erase it from the screen even
        # though it was already correctly delivered. Appending to a list
        # while iterating it forward like this is well-defined in Python (the
        # loop picks up items appended before it reaches the current end).
        transcripts = []
        for text in self.committed_texts:
            # Checked every iteration, not just once at the end: a further
            # language change means this one is already stale, so stop
            # spending DeepL calls translating text nobody will see translated
            # this way.
            if generation != self._retranslation_generation:
                return
            translated_text: str | None = None
            try:
                translated_text = await deepl.translate(text, target_language)
            except Exception:
                logger.exception("Could not retranslate transcript")
            transcripts.append(
                Transcript(
                    original_text=text,
                    translated_text=translated_text,
                    target_language=target_language,
                )
            )

        # Also checked once more here, not just per-iteration above: the very
        # last iteration's own translate call can itself be what a newer
        # language change races against - the loop would otherwise exit
        # normally afterward and still send this now-stale result.
        if generation != self._retranslation_generation:
            return

        try:
            await self.send(
                RetranslatedTranscripts(
                    target_language=target_language, transcripts=transcripts
                ).model_dump()
            )
        except WebSocketDisconnect:
            pass

    async def _persist_target_language(self, session_id: str, target_language: str) -> None:
        try:
            # self.user, not a captured value: same reasoning as save_message
            # above - use whatever token is current when this actually runs.
            await supabase.update_session_target_language(self.user, session_id, target_language)
        except Exception:
            logger.exception("Could not update session target language")

    async def _end_db_session(self) -> None:
        if self.db_session_id is None:
            return
        try:
            await supabase.end_session(self.user, self.db_session_id)
        except Exception:
            logger.exception("Could not end Supabase session")
        self.db_session_id = None

    async def _cleanup(self) -> None:
        # Same graceful wind-down as an explicit stop_transcription: closing
        # the connection (disconnect, an auth rejection) must not cancel a
        # committed transcript that's already mid-translate/mid-save. Merely
        # cancelling the relay/worker tasks here (the previous behavior)
        # silently dropped whatever was still in flight.
        #
        # run() is itself cancelled the moment the connection closes (a real
        # client disconnect delivers "websocket.disconnect" and lets the app
        # keep running, but the ASGI test client's teardown cancels the whole
        # app task right after sending it) - so plain `await
        # self._stop_transcription()` here would itself get cut short.
        # asyncio.shield() decouples _stop_transcription from that
        # cancellation; the loop re-awaits it if our own await-of-the-shield
        # is what got cancelled, only letting a cancellation through once
        # _stop_transcription has actually finished.
        cleanup_task = asyncio.ensure_future(self._stop_transcription())
        while True:
            try:
                await asyncio.shield(cleanup_task)
                return
            except asyncio.CancelledError:
                if cleanup_task.done():
                    raise


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ConnectionHandler(websocket).run()
