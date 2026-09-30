import asyncio

import pytest

from services import live_rooms
from services.live_rooms import LiveRoom, LiveRoomRegistry


class FakeViewer:
    def __init__(self, *, fail: bool = False, delay: float = 0.0):
        self.received: list[dict] = []
        self.fail = fail
        self.delay = delay

    async def send(self, payload: dict) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("boom")
        self.received.append(payload)


@pytest.fixture(autouse=True)
def fake_deepl(monkeypatch):
    async def fake_translate(text: str, target_language: str) -> str:
        return f"[{target_language}] {text}"

    async def fake_translate_many(texts: list[str], target_language: str) -> list[str | None]:
        return [f"[{target_language}] {text}" for text in texts]

    monkeypatch.setattr(live_rooms.deepl, "translate", fake_translate)
    monkeypatch.setattr(live_rooms.deepl, "translate_many", fake_translate_many)


async def _drain(room: LiveRoom) -> None:
    await room._queue.join()


async def test_publish_broadcasts_translated_line_to_viewers_in_their_own_language():
    room = LiveRoom(session_id="s1", title="Test", source_language="es")
    room.start_worker()
    viewer_fr = FakeViewer()
    viewer_de = FakeViewer()
    room.add_viewer(viewer_fr, "fr")
    room.add_viewer(viewer_de, "de")

    room.publish("hola", None, None)
    await _drain(room)
    await room.stop_worker()

    assert viewer_fr.received == [
        {"type": "live_line", "index": 0, "original_text": "hola", "translated_text": "[fr] hola", "target_language": "fr"}
    ]
    assert viewer_de.received == [
        {"type": "live_line", "index": 0, "original_text": "hola", "translated_text": "[de] hola", "target_language": "de"}
    ]


async def test_publish_stores_the_message_id_on_the_line_for_later_audio_lookup():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.start_worker()

    room.publish("hola", None, None, message_id="msg-1")
    await _drain(room)
    await room.stop_worker()

    assert room.lines[0].message_id == "msg-1"


async def test_publish_can_take_a_pending_message_id_that_resolves_later():
    # KAN-65: the owner publishes a line before its Supabase save finishes,
    # so the id arrives after the line itself.
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    viewer = FakeViewer()
    room.add_viewer(viewer, "fr")
    room.start_worker()
    save: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()

    room.publish("hola", None, None, message_id=save)
    await _drain(room)

    # Delivered to viewers without waiting on the save.
    assert [m["type"] for m in viewer.received] == ["live_line"]
    assert room.lines[0].message_id is None

    save.set_result("msg-1")
    assert await room.lines[0].resolved_message_id() == "msg-1"
    assert room.lines[0].message_id == "msg-1"
    await room.stop_worker()


async def test_resolved_message_id_is_none_when_the_pending_save_fails():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.start_worker()
    save: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()

    room.publish("hola", None, None, message_id=save)
    await _drain(room)
    save.set_result(None)

    assert await room.lines[0].resolved_message_id() is None
    await room.stop_worker()


async def test_resolved_message_id_gives_up_after_a_timeout():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.start_worker()
    save: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()

    room.publish("hola", None, None, message_id=save)
    await _drain(room)

    assert await room.lines[0].resolved_message_id(timeout=0.01) is None
    # A late save still lands for the next request.
    save.set_result("msg-1")
    assert await room.lines[0].resolved_message_id() == "msg-1"
    await room.stop_worker()


async def test_resolved_message_id_returns_a_known_id_immediately():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.start_worker()

    room.publish("hola", None, None, message_id="msg-1")
    await _drain(room)

    assert await room.lines[0].resolved_message_id() == "msg-1"
    await room.stop_worker()


async def test_publish_without_a_message_id_defaults_to_none():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.start_worker()

    room.publish("hola", None, None)
    await _drain(room)
    await room.stop_worker()

    assert room.lines[0].message_id is None


async def test_publish_seeds_translation_cache_from_owner_without_extra_deepl_call():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.start_worker()
    viewer = FakeViewer()
    room.add_viewer(viewer, "fr")

    room.publish("hola", "fr", "owner's own translation")
    await _drain(room)
    await room.stop_worker()

    assert viewer.received[0]["translated_text"] == "owner's own translation"


async def test_publish_never_awaits_translation_or_viewer_io():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    # No worker started: publish() must return immediately regardless, since
    # the owner's transcript-save path calls it synchronously without a task.
    room.publish("hola", None, None)
    assert room._queue.qsize() == 1


async def test_a_failed_or_slow_viewer_send_does_not_block_other_viewers():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.start_worker()
    failing = FakeViewer(fail=True)
    healthy = FakeViewer()
    room.add_viewer(failing, "fr")
    room.add_viewer(healthy, "fr")

    room.publish("hola", None, None)
    await _drain(room)
    await room.stop_worker()

    assert healthy.received[0]["translated_text"] == "[fr] hola"


async def test_lines_preserve_publish_order_and_increasing_index():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.start_worker()
    viewer = FakeViewer()
    room.add_viewer(viewer, "fr")

    room.publish("uno", None, None)
    room.publish("dos", None, None)
    room.publish("tres", None, None)
    await _drain(room)
    await room.stop_worker()

    assert [line["index"] for line in viewer.received] == [0, 1, 2]
    assert [line["original_text"] for line in viewer.received] == ["uno", "dos", "tres"]


async def test_ensure_language_fills_gaps_for_every_existing_line():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.lines = [
        live_rooms.RoomLine(index=0, original_text="uno", translations={"fr": "un"}),
        live_rooms.RoomLine(index=1, original_text="dos"),
    ]

    await room.ensure_language("de")

    assert room.lines[0].translations["de"] == "[de] uno"
    assert room.lines[1].translations["de"] == "[de] dos"
    # Already-cached language for line 0 is untouched.
    assert room.lines[0].translations["fr"] == "un"


async def test_ensure_language_is_a_no_op_when_nothing_is_missing():
    calls = []

    async def tracking_translate_many(texts, target_language):
        calls.append(texts)
        return [f"[{target_language}] {t}" for t in texts]

    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.lines = [live_rooms.RoomLine(index=0, original_text="uno", translations={"fr": "un"})]

    await room.ensure_language("fr")

    assert calls == []


async def test_ensure_language_survives_a_translate_many_failure(monkeypatch):
    # translate_many's own per-chunk resilience only covers HTTP failures -
    # a config error (e.g. DEEPL_API_KEY unset) raises before ever reaching
    # that loop. ensure_language has no caller-side try/except of its own
    # (routers/viewer_ws.py's join_live/set_viewer_language don't guard it),
    # so it must not let that propagate and kill the viewer's socket.
    async def failing_translate_many(texts, target_language):
        raise RuntimeError("DEEPL_API_KEY is set but empty")

    monkeypatch.setattr(live_rooms.deepl, "translate_many", failing_translate_many)

    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.lines = [live_rooms.RoomLine(index=0, original_text="uno")]

    await room.ensure_language("fr")

    assert room.lines[0].translations["fr"] is None


def test_snapshot_returns_lines_in_a_given_language():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.lines = [
        live_rooms.RoomLine(index=0, original_text="uno", translations={"fr": "un"}),
        live_rooms.RoomLine(index=1, original_text="dos", translations={}),
    ]

    assert room.snapshot("fr") == [
        {"index": 0, "original_text": "uno", "translated_text": "un"},
        {"index": 1, "original_text": "dos", "translated_text": None},
    ]


def test_seed_history_loads_stored_messages_as_lines():
    room = LiveRoom(session_id="s1", title=None, source_language=None)

    room.seed_history(
        [
            {"id": "m1", "original_text": "hola", "translated_text": "hello", "target_language": "en"},
            {"id": "m2", "original_text": "mundo", "translated_text": None, "target_language": None},
        ]
    )

    assert [line.index for line in room.lines] == [0, 1]
    assert room.lines[0].original_text == "hola"
    assert room.lines[0].translations == {"en": "hello"}
    assert room.lines[0].message_id == "m1"
    assert room.lines[1].translations == {}
    assert room.snapshot("en")[0]["translated_text"] == "hello"


def test_seed_history_is_a_no_op_on_a_room_that_already_has_lines():
    # A second owner connection (another tab) joining an already-live room
    # must not append the stored history a second time.
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.seed_history([{"id": "m1", "original_text": "hola", "translated_text": None, "target_language": None}])

    room.seed_history([{"id": "m1", "original_text": "hola", "translated_text": None, "target_language": None}])

    assert len(room.lines) == 1


async def test_lines_published_after_seeding_continue_the_index():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.seed_history([{"id": "m1", "original_text": "hola", "translated_text": None, "target_language": None}])
    room.start_worker()

    room.publish("mundo", None, None)
    await _drain(room)
    await room.stop_worker()

    assert [line.index for line in room.lines] == [0, 1]


async def test_broadcast_status_updates_state_and_notifies_viewers():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    viewer = FakeViewer()
    room.add_viewer(viewer, "fr")

    await room.broadcast_status("recording")

    assert room.state == "recording"
    assert viewer.received == [{"type": "live_status", "state": "recording"}]


async def test_broadcast_status_with_no_viewers_still_updates_state():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    await room.broadcast_status("ended")
    assert room.state == "ended"


async def test_broadcast_status_does_not_raise_when_a_viewer_send_fails():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    room.add_viewer(FakeViewer(fail=True), "fr")
    await room.broadcast_status("paused")
    assert room.state == "paused"


def test_add_update_remove_viewer():
    room = LiveRoom(session_id="s1", title=None, source_language=None)
    viewer = FakeViewer()
    viewer_id = room.add_viewer(viewer, "fr")
    assert room.viewers[viewer_id] == (viewer, "fr")

    room.update_viewer_language(viewer_id, "de")
    assert room.viewers[viewer_id] == (viewer, "de")

    room.remove_viewer(viewer_id)
    assert viewer_id not in room.viewers


async def test_registry_acquire_creates_and_reuses_a_room_by_token():
    registry = LiveRoomRegistry()
    room1 = registry.acquire("token-1", session_id="s1", title="T", source_language="es")
    room2 = registry.acquire("token-1", session_id="s1", title="T", source_language="es")

    assert room1 is room2
    assert room1.refcount == 2
    await room1.stop_worker()


async def test_registry_release_stops_worker_and_drops_room_at_zero_refcount():
    registry = LiveRoomRegistry()
    registry.acquire("token-1", session_id="s1", title=None, source_language=None)
    room = registry.acquire("token-1", session_id="s1", title=None, source_language=None)
    assert room.refcount == 2

    await registry.release("token-1")
    assert registry.get("token-1") is room
    assert room.refcount == 1

    await registry.release("token-1")
    assert registry.get("token-1") is None


async def test_registry_release_of_unknown_token_is_a_no_op():
    registry = LiveRoomRegistry()
    await registry.release("does-not-exist")
