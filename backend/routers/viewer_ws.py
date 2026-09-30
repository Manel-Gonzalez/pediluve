import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from models.messages import ErrorMessage
from models.viewer import (
    AudioFailed,
    AudioReady,
    JoinLive,
    LiveJoined,
    LiveLineOut,
    LiveLinesRetranslated,
    RequestAudio,
    SetViewerLanguage,
)
from services import deepl, live_rooms, tts_cache

logger = logging.getLogger(__name__)

router = APIRouter()

# Same value as routers.ws.SESSION_NOT_FOUND_CLOSE_CODE, kept as its own
# constant rather than imported from there - this endpoint has no
# dependency on ws.py at all, matching KAN-50's separate-handler design
# (see docs/decisions.md D1): a viewer identity never shares a code path
# with an owner's.
LIVE_NOT_AVAILABLE_CLOSE_CODE = 4404


class ViewerConnectionHandler:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.send_lock = asyncio.Lock()
        self.room: live_rooms.LiveRoom | None = None
        self.viewer_id: int | None = None
        self.target_language: str | None = None
        self._closed = False

    async def send(self, payload: dict) -> None:
        async with self.send_lock:
            await self.websocket.send_json(payload)

    async def run(self) -> None:
        await self.websocket.accept()
        try:
            first = await self.websocket.receive()
            if first["type"] == "websocket.disconnect":
                return
            if first.get("text") is None:
                await self._reject("First message must be join_live")
                return
            if not await self._handle_join_live(first["text"]):
                return

            while True:
                message = await self.websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("text") is None:
                    continue
                await self._handle_text_message(message["text"])
                if self._closed:
                    break
        except WebSocketDisconnect:
            logger.info("Viewer disconnected")
        finally:
            self._cleanup()

    async def _reject(self, message: str, code: int = LIVE_NOT_AVAILABLE_CLOSE_CODE) -> None:
        async with self.send_lock:
            await self.websocket.send_json(ErrorMessage(message=message).model_dump())
            await self.websocket.close(code=code)
        self._closed = True

    async def _handle_join_live(self, raw: str) -> bool:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            await self._reject(f"Invalid message: {exc}")
            return False

        if data.get("type") != "join_live":
            await self._reject("First message must be join_live")
            return False

        try:
            request = JoinLive.model_validate(data)
        except ValidationError as exc:
            await self._reject(f"Invalid message: {exc}")
            return False

        if request.target_language not in deepl.SUPPORTED_TARGET_LANGUAGES:
            await self._reject(f"Unsupported target language: {request.target_language}")
            return False

        room = live_rooms.registry.get(request.share_token)
        # Deliberately indistinguishable from "session isn't live right now":
        # a viewer never reads Postgres (see docs/decisions.md D3), and a
        # room only exists for the lifetime of a live owner connection, so
        # there's no way from here to tell "unknown token" apart from
        # "known token, nobody's recording" - and no reason a stranger
        # holding a link should be able to tell them apart either.
        if room is None:
            await self._reject("Live session not available")
            return False

        self.room = room
        self.target_language = request.target_language
        await room.ensure_language(request.target_language)
        self.viewer_id = room.add_viewer(self, request.target_language)

        await self.send(
            LiveJoined(
                title=room.title,
                source_language=room.source_language,
                target_language=request.target_language,
                state=room.state,
                lines=[LiveLineOut(**line) for line in room.snapshot(request.target_language)],
            ).model_dump()
        )
        return True

    async def _handle_text_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            await self.send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
            return

        msg_type = data.get("type")

        if msg_type == "set_viewer_language":
            await self._handle_set_viewer_language(data)
            return

        if msg_type == "request_audio":
            await self._handle_request_audio(data)
            return

        await self.send(ErrorMessage(message=f"Unknown message type: {msg_type}").model_dump())

    async def _handle_set_viewer_language(self, data: dict) -> None:
        try:
            request = SetViewerLanguage.model_validate(data)
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

        assert self.room is not None and self.viewer_id is not None
        self.target_language = request.target_language
        await self.room.ensure_language(request.target_language)
        self.room.update_viewer_language(self.viewer_id, request.target_language)

        await self.send(
            LiveLinesRetranslated(
                target_language=request.target_language,
                lines=[LiveLineOut(**line) for line in self.room.snapshot(request.target_language)],
            ).model_dump()
        )

    async def _handle_request_audio(self, data: dict) -> None:
        try:
            request = RequestAudio.model_validate(data)
        except ValidationError as exc:
            await self.send(ErrorMessage(message=f"Invalid message: {exc}").model_dump())
            return

        assert self.room is not None
        index = request.index
        if index < 0 or index >= len(self.room.lines):
            await self.send(AudioFailed(index=index, message="No such line").model_dump())
            return

        line = self.room.lines[index]
        language = self.target_language
        translated_text = line.translations.get(language)

        # Every one of these is "can't offer playback for this line right
        # now" - a translation that hasn't arrived or failed (no text to
        # speak), (shouldn't happen while a room exists, but defensive) no
        # owner connection to borrow credentials from, or a save that failed
        # (no message_id, see routers/ws.py). The id can still be on its way:
        # lines reach viewers before the owner's save finishes (KAN-65), and
        # "Listen live" asks for audio the moment a line arrives.
        if translated_text is None or self.room.owner_user is None:
            await self.send(AudioFailed(index=index, message="Audio unavailable").model_dump())
            return
        message_id = await line.resolved_message_id()
        if message_id is None:
            await self.send(AudioFailed(index=index, message="Audio unavailable").model_dump())
            return

        try:
            audio_url, cached = await tts_cache.get_or_create_audio_url(
                self.room.owner_user, self.room.session_id, message_id, translated_text, language
            )
        except Exception:
            logger.exception("Could not generate audio for message %s (%s)", message_id, language)
            await self.send(AudioFailed(index=index, message="Audio unavailable").model_dump())
            return

        await self.send(
            AudioReady(index=index, target_language=language, audio_url=audio_url, cached=cached).model_dump()
        )

    def _cleanup(self) -> None:
        if self.room is not None and self.viewer_id is not None:
            self.room.remove_viewer(self.viewer_id)


@router.websocket("/ws/view")
async def viewer_websocket_endpoint(websocket: WebSocket) -> None:
    await ViewerConnectionHandler(websocket).run()
