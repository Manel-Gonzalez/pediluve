import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from models.messages import (
    Authenticate,
    Authenticated,
    ClientMessage,
    EchoMessage,
    ErrorMessage,
    JoinSession,
    PartialTranscript,
    RetranslatedTranscripts,
    SessionJoined,
    SetTargetLanguage,
    StartTranscription,
    Transcript,
)
from services import deepl, live_rooms, supabase
from services.auth import AuthenticatedUser, AuthError, AuthServiceUnavailable, verify_access_token
from services.elevenlabs import RealtimeTranscriptionSession

AUTH_REQUIRED_CLOSE_CODE = 4401
# Distinct from AUTH_REQUIRED_CLOSE_CODE: the token wasn't necessarily bad,
# Supabase Auth just couldn't be reached - a client should retry, not treat
# this like an invalid session and force a re-login (see services/auth.py).
AUTH_SERVICE_UNAVAILABLE_CLOSE_CODE = 4503
# A join_session naming an id that doesn't exist, isn't a valid UUID, or
# isn't visible to this user under RLS - all three look identical from the
# client's side of RLS, so they're reported and closed the same way.
SESSION_NOT_FOUND_CLOSE_CODE = 4404

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
        # on. Deliberately NOT reset per recording, same as sequence and
        # db_session_id: all three are seeded once by join_session and carry
        # across every pause/resume cycle in the same visit, because they all
        # describe the one underlying DB session, not a single recording
        # take. The frontend's own transcriptRows accumulates the same way
        # (never cleared on a fresh start_transcription), and
        # retranslated_transcripts wholesale-replaces that list - resetting
        # this per recording would silently drop every earlier take's rows
        # from the screen the next time the language changes.
        self.committed_texts: list[str] = []
        # Set on a successful join_session, cleared on disconnect (KAN-50's
        # QR live viewer) - the in-memory room anonymous /ws/view viewers
        # attach to. Acquired once per visit (survives pause/resume, same
        # lifecycle as db_session_id), released only when this connection's
        # own session actually ends (_end_db_session), not on a pause.
        self.live_room: live_rooms.LiveRoom | None = None
        self.share_token: str | None = None
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
        # _pause_transcription can wait for it before returning.
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
        if self.live_room is not None:
            # Keeps the room's copy current across a token refresh - a
            # viewer's request_audio (KAN-58) borrows whatever's here to
            # write the TTS cache, so a stale/expired token here would fail
            # that write with no way for the owner to see why.
            self.live_room.owner_user = authenticated_user
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

        if msg_type == "join_session":
            await self._join_session(data)
            return

        if msg_type == "start_transcription":
            await self._start_transcription(data)
            return

        if msg_type == "stop_transcription":
            await self._pause_transcription()
            return

        if msg_type == "set_target_language":
            if self.db_session_id is None:
                await self.send(
                    ErrorMessage(message="Join a session before setting the target language").model_dump()
                )
                return
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

    async def _join_session(self, data: dict) -> None:
        if self.db_session_id is not None:
            await self.send(ErrorMessage(message="Session already joined").model_dump())
            return

        try:
            request = JoinSession.model_validate(data)
        except ValidationError as exc:
            await self.send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
            return

        try:
            uuid.UUID(request.session_id)
        except ValueError:
            await self._reject("Session not found", code=SESSION_NOT_FOUND_CLOSE_CODE)
            return

        try:
            row = await supabase.get_session_with_messages(self.user, request.session_id)
        except Exception:
            logger.exception("Could not load session")
            await self.send(ErrorMessage(message="Could not load session").model_dump())
            return

        if row is None:
            await self._reject("Session not found", code=SESSION_NOT_FOUND_CLOSE_CODE)
            return

        # RLS doesn't (yet) rule this out on its own - once guest RLS lands
        # (KAN-59) a row can be visible to a non-owner too, and the live/
        # recording owner view must never be reachable that way. Reported
        # identically to "doesn't exist", same as every other join_session
        # failure - a guest gets no signal either way.
        if row["user_id"] != self.user.id:
            await self._reject("Session not found", code=SESSION_NOT_FOUND_CLOSE_CODE)
            return

        messages = row["messages"]
        self.db_session_id = row["id"]
        self.sequence = max((message["sequence"] for message in messages), default=-1) + 1
        self.committed_texts = [message["original_text"] for message in messages]
        self.source_language = row["source_language"]
        self.target_language = row["target_language"]
        self.share_token = row["share_token"]
        self.live_room = live_rooms.registry.acquire(
            self.share_token,
            session_id=row["id"],
            title=row["title"],
            source_language=row["source_language"],
        )
        self.live_room.owner_user = self.user

        await self.send(
            SessionJoined(
                session_id=row["id"],
                title=row["title"],
                source_language=row["source_language"],
                target_language=row["target_language"],
                transcripts=[
                    Transcript(
                        original_text=message["original_text"],
                        translated_text=message["translated_text"],
                        target_language=message["target_language"],
                    )
                    for message in messages
                ],
                share_token=self.share_token,
            ).model_dump()
        )

    async def _start_transcription(self, data: dict) -> None:
        if self.stt_session is not None:
            return

        if self.db_session_id is None:
            await self.send(
                ErrorMessage(message="Join a session before starting transcription").model_dump()
            )
            return

        try:
            request = StartTranscription.model_validate(data)
        except ValidationError as exc:
            await self.send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
            return

        # Captured for display/persistence and a future re-translation use. Not
        # yet passed to RealtimeTranscriptionSession.connect(): whether
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
        if self.source_language is not None:
            # Fire-and-forget, like _persist_target_language below: a resume
            # can re-state the source language (e.g. after a stop/start with a
            # different mic setup), and the main receive loop must not stall
            # on the write.
            self._spawn_background(
                self._persist_source_language(self.db_session_id, self.source_language)
            )

        # Committed transcripts are queued rather than awaited inline here, so a
        # slow (or slow-to-fail) DeepL call can't stall relaying the next partial/
        # committed event off the ElevenLabs connection. A single worker drains the
        # queue in order, which keeps sequence numbers and message order correct.
        self.transcript_queue = asyncio.Queue()
        self.relay_task = asyncio.create_task(self._relay_transcripts(session))
        self.transcript_worker_task = asyncio.create_task(self._process_transcript_queue())

        if self.live_room is not None:
            await self.live_room.broadcast_status("recording")

    async def _pause_transcription(self) -> None:
        # Winds down the current recording take only - db_session_id (and
        # everything seeded from it: sequence, committed_texts, source/target
        # language) is untouched, so a later start_transcription resumes the
        # same session instead of needing a fresh join_session. Ending the DB
        # session itself is _cleanup's job alone (see there for why).
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
        self.stt_session = None
        self.relay_task = None
        self.transcript_queue = None
        self.transcript_worker_task = None

        if self.live_room is not None:
            await self.live_room.broadcast_status("paused")

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

        message_id: str | None = None
        if self.db_session_id is not None:
            try:
                # self.user read here, not captured earlier in this method - if a
                # re-authenticate swapped it while the DeepL call above was in
                # flight, this save uses the new token, per KAN-18.
                saved = await supabase.save_message(
                    self.user,
                    self.db_session_id,
                    self.sequence,
                    text,
                    translated_text=translated_text,
                    target_language=target_language,
                )
                message_id = saved["id"]
                self.sequence += 1
            except Exception:
                logger.exception("Could not save message to Supabase")

        if self.live_room is not None:
            # Never awaited: publish() only queues, so a slow/failing
            # viewer-side translation or send can never stall this worker
            # (see services/live_rooms.py and docs/decisions.md's D4).
            # message_id stays None if the save above failed - that line
            # just can't offer playback (KAN-58), nothing else changes.
            self.live_room.publish(text, target_language, translated_text, message_id=message_id)

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

    async def _persist_source_language(self, session_id: str, source_language: str) -> None:
        try:
            await supabase.update_session_source_language(self.user, session_id, source_language)
        except Exception:
            logger.exception("Could not update session source language")

    async def _end_db_session(self) -> None:
        if self.db_session_id is None:
            return
        try:
            await supabase.end_session(self.user, self.db_session_id)
        except Exception:
            logger.exception("Could not end Supabase session")
        self.db_session_id = None

        if self.live_room is not None:
            await self.live_room.broadcast_status("ended")
            await live_rooms.registry.release(self.share_token)
            self.live_room = None
            self.share_token = None

    async def _pause_and_end(self) -> None:
        await self._pause_transcription()
        # Ending the DB session lives here, not in _pause_transcription: a
        # stop_transcription message is a pause the same connection can
        # resume from (start_transcription again, no re-join needed), while
        # disconnecting is leaving the session's live view entirely. Doing it
        # only here means ended_at is written exactly once per visit, on
        # disconnect - not on every stop/start cycle within one.
        await self._end_db_session()

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
        # self._pause_and_end()` here would itself get cut short.
        # asyncio.shield() decouples it from that cancellation; the loop
        # re-awaits it if our own await-of-the-shield is what got cancelled,
        # only letting a cancellation through once it has actually finished.
        cleanup_task = asyncio.ensure_future(self._pause_and_end())
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
