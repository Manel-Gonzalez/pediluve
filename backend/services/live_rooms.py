import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

from services import deepl
from services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

# Bounds how long the room worker waits on one viewer's socket write before
# giving up on that viewer and moving on - a single stalled connection must
# never stall delivery to every other viewer in the room (see KAN-50's D4).
_SEND_TIMEOUT_SECONDS = 5.0

# How long a viewer's request_audio waits for the owner's Supabase save to
# produce a message_id (KAN-65: lines go out before their save finishes).
_MESSAGE_ID_TIMEOUT_SECONDS = 10.0


class Viewer(Protocol):
    async def send(self, payload: dict) -> None: ...


@dataclass
class RoomLine:
    index: int
    original_text: str
    # Keyed by target language code; a value of None means translation was
    # attempted and failed (distinct from "not attempted yet" - a missing key).
    translations: dict[str, str | None] = field(default_factory=dict)
    # The DB messages.id this line was saved as, or None if the save failed
    # (see routers/ws.py::_handle_committed_transcript) - request_audio
    # (KAN-58) needs this to key the message_audio cache; a line with no
    # message_id simply can't offer playback.
    message_id: str | None = None
    # KAN-65: the owner publishes a line as soon as it's translated, before
    # its Supabase save finishes, so the id can still be on its way. Set to
    # that save while it's pending; resolved_message_id() waits on it.
    pending_message_id: asyncio.Future[str | None] | None = None

    async def resolved_message_id(self, timeout: float = _MESSAGE_ID_TIMEOUT_SECONDS) -> str | None:
        pending = self.pending_message_id
        if pending is None:
            return self.message_id
        try:
            # shield(): a viewer's timeout must not cancel the owner's save.
            message_id = await asyncio.wait_for(asyncio.shield(pending), timeout)
        except Exception:
            # Timed out, or the save itself raised - no id to key audio on.
            return None
        self.message_id = message_id
        self.pending_message_id = None
        return message_id


class LiveRoom:
    # One per session with an owner connection currently live. Populated
    # entirely by the owner's own connection (its own RLS-scoped reads, its
    # own committed lines, its own translation) - anonymous viewers never
    # touch Postgres, see docs/decisions.md.
    def __init__(self, session_id: str, title: str | None, source_language: str | None):
        self.session_id = session_id
        self.title = title
        self.source_language = source_language
        self.state = "paused"
        self.lines: list[RoomLine] = []
        # id -> (viewer, target_language); a plain incrementing id rather
        # than the viewer object itself as the key, so add/remove/update are
        # all simple dict operations without requiring Viewer to be hashable.
        self.viewers: dict[int, tuple[Viewer, str]] = {}
        self.refcount = 0
        self._queue: asyncio.Queue[tuple[str, str | None, str | None, str | None]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._next_viewer_id = 0
        # The live owner connection's own AuthenticatedUser, kept current by
        # routers/ws.py (set on join, refreshed on re-authenticate) - a
        # viewer's request_audio (KAN-58) borrows this to write the TTS
        # cache under the owner's RLS-scoped credentials, never its own
        # (an anonymous viewer has no Supabase identity at all, see D3).
        self.owner_user: AuthenticatedUser | None = None

    def start_worker(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._run_worker())

    async def stop_worker(self) -> None:
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        self._worker_task = None

    def set_status(self, state: str) -> None:
        self.state = state

    def seed_history(self, messages: list[dict]) -> None:
        # A room is created empty on the first owner join_session, but the
        # session may already have stored messages - earlier takes, or a
        # previous owner connection whose room died with a backend restart
        # or a page reload. Without this a viewer (or one refreshing its
        # page) would only ever see lines said since this room was created,
        # while the owner's own view shows the whole history. `messages` is
        # the owner's own RLS-scoped join_session read, so viewers still
        # never touch Postgres (D3). Only on a still-empty room: a second
        # owner tab joining an already-live room must not append it twice.
        if self.lines:
            return
        for message in messages:
            line = RoomLine(
                index=len(self.lines),
                original_text=message["original_text"],
                message_id=message.get("id"),
            )
            if message.get("target_language") is not None:
                line.translations[message["target_language"]] = message.get("translated_text")
            self.lines.append(line)

    async def broadcast_status(self, state: str) -> None:
        # Unlike publish(), this never involves DeepL, so it's cheap enough
        # to send directly rather than going through the queue - but still
        # per-viewer timeout-guarded, same reasoning as _broadcast_line.
        self.state = state
        if not self.viewers:
            return

        async def _send_to(viewer: Viewer) -> None:
            try:
                await asyncio.wait_for(
                    viewer.send({"type": "live_status", "state": state}),
                    timeout=_SEND_TIMEOUT_SECONDS,
                )
            except Exception:
                logger.warning("Dropped a live_status send to a slow or failed viewer")

        await asyncio.gather(*(_send_to(viewer) for viewer, _ in self.viewers.values()))

    def publish(
        self,
        original_text: str,
        owner_target_language: str | None,
        owner_translated_text: str | None,
        message_id: str | asyncio.Future[str | None] | None = None,
    ) -> None:
        # Never awaits - called synchronously from the owner's committed-
        # transcript path, which must not be slowed by viewer translation
        # calls or viewer socket I/O. message_id may be the owner's still-
        # running save (KAN-65) rather than an id - see RoomLine.
        self._queue.put_nowait((original_text, owner_target_language, owner_translated_text, message_id))

    async def _run_worker(self) -> None:
        while True:
            original_text, owner_target_language, owner_translated_text, message_id = (
                await self._queue.get()
            )
            try:
                await self._publish_one(
                    original_text, owner_target_language, owner_translated_text, message_id
                )
            except Exception:
                logger.exception("Could not publish a line to live room %s", self.session_id)
            finally:
                self._queue.task_done()

    async def _publish_one(
        self,
        original_text: str,
        owner_target_language: str | None,
        owner_translated_text: str | None,
        message_id: str | asyncio.Future[str | None] | None,
    ) -> None:
        line = RoomLine(index=len(self.lines), original_text=original_text)
        if isinstance(message_id, asyncio.Future):
            line.pending_message_id = message_id
        else:
            line.message_id = message_id
        if owner_target_language is not None:
            # Seeds the cache with the owner's own translation - zero extra
            # DeepL cost for a viewer whose language happens to match it.
            line.translations[owner_target_language] = owner_translated_text
        self.lines.append(line)

        languages = {language for _, language in self.viewers.values()}
        missing = sorted(languages - line.translations.keys())
        if missing:
            results = await asyncio.gather(
                *(deepl.translate(original_text, language) for language in missing),
                return_exceptions=True,
            )
            for language, result in zip(missing, results):
                if isinstance(result, Exception):
                    logger.exception("Could not translate a live line to %s", language, exc_info=result)
                    line.translations[language] = None
                else:
                    line.translations[language] = result

        await self._broadcast_line(line)

    async def _broadcast_line(self, line: RoomLine) -> None:
        if not self.viewers:
            return

        async def _send_to(viewer: Viewer, language: str) -> None:
            try:
                await asyncio.wait_for(
                    viewer.send(
                        {
                            "type": "live_line",
                            "index": line.index,
                            "original_text": line.original_text,
                            "translated_text": line.translations.get(language),
                            "target_language": language,
                        }
                    ),
                    timeout=_SEND_TIMEOUT_SECONDS,
                )
            except Exception:
                logger.warning("Dropped a live_line send to a slow or failed viewer")

        await asyncio.gather(*(_send_to(viewer, language) for viewer, language in self.viewers.values()))

    async def ensure_language(self, target_language: str) -> None:
        # Fills every gap for a language that's about to be shown to a
        # viewer (a fresh join, or an existing viewer switching languages).
        # Batched via translate_many rather than per-line, since this can
        # cover the whole history accumulated so far in one request.
        missing_indices = [
            index for index, line in enumerate(self.lines) if target_language not in line.translations
        ]
        if not missing_indices:
            return
        texts = [self.lines[index].original_text for index in missing_indices]
        try:
            results = await deepl.translate_many(texts, target_language)
        except Exception:
            # translate_many's own per-chunk resilience only covers HTTP
            # failures - a config error (DEEPL_API_KEY unset/blank) raises
            # before ever reaching that loop. Callers (routers/viewer_ws.py's
            # join_live/set_viewer_language) have no try/except of their own
            # around this call, so letting it propagate would silently kill
            # the viewer's socket instead of sending an error - same
            # "translation unavailable" fallback as a genuine per-chunk
            # failure keeps this resilient either way.
            logger.exception("Could not fill translation gaps for %s", target_language)
            results = [None] * len(missing_indices)
        for index, result in zip(missing_indices, results):
            self.lines[index].translations[target_language] = result

    def snapshot(self, target_language: str) -> list[dict]:
        return [
            {
                "index": line.index,
                "original_text": line.original_text,
                "translated_text": line.translations.get(target_language),
            }
            for line in self.lines
        ]

    def add_viewer(self, viewer: Viewer, target_language: str) -> int:
        viewer_id = self._next_viewer_id
        self._next_viewer_id += 1
        self.viewers[viewer_id] = (viewer, target_language)
        return viewer_id

    def update_viewer_language(self, viewer_id: int, target_language: str) -> None:
        viewer, _ = self.viewers[viewer_id]
        self.viewers[viewer_id] = (viewer, target_language)

    def remove_viewer(self, viewer_id: int) -> None:
        self.viewers.pop(viewer_id, None)


class LiveRoomRegistry:
    # One process-wide instance (the module-level `registry` below). Owner
    # connections are the only writers: acquire() on join/resume, release()
    # on pause/disconnect - a room lives exactly as long as at least one
    # owner connection for its session is live (KAN-50's D4).
    def __init__(self) -> None:
        self._rooms: dict[str, LiveRoom] = {}

    def acquire(
        self, share_token: str, session_id: str, title: str | None, source_language: str | None
    ) -> LiveRoom:
        room = self._rooms.get(share_token)
        if room is None:
            room = LiveRoom(session_id=session_id, title=title, source_language=source_language)
            self._rooms[share_token] = room
        room.refcount += 1
        room.start_worker()
        return room

    async def release(self, share_token: str) -> None:
        room = self._rooms.get(share_token)
        if room is None:
            return
        room.refcount -= 1
        if room.refcount <= 0:
            await room.stop_worker()
            self._rooms.pop(share_token, None)

    def get(self, share_token: str) -> LiveRoom | None:
        return self._rooms.get(share_token)


registry = LiveRoomRegistry()
