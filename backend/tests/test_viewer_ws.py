import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDisconnect

from main import app
import routers.viewer_ws as viewer_ws_module
from services import live_rooms

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_live_room_registry():
    live_rooms.registry._rooms.clear()
    yield
    live_rooms.registry._rooms.clear()


@pytest.fixture(autouse=True)
def fake_deepl(monkeypatch):
    async def fake_translate(text, target_language):
        return f"[{target_language}] {text}"

    async def fake_translate_many(texts, target_language):
        return [f"[{target_language}] {text}" for text in texts]

    monkeypatch.setattr("routers.viewer_ws.deepl.translate", fake_translate)
    monkeypatch.setattr("routers.viewer_ws.deepl.translate_many", fake_translate_many)


def _make_room(*, state="recording", title="Standup", source_language="en", lines=None):
    share_token = str(uuid.uuid4())
    room = live_rooms.LiveRoom(session_id="session-1", title=title, source_language=source_language)
    room.state = state
    for line in lines or []:
        room.lines.append(
            live_rooms.RoomLine(
                index=line["index"],
                original_text=line["original_text"],
                translations=line.get("translations", {}),
            )
        )
    live_rooms.registry._rooms[share_token] = room
    return share_token, room


@contextmanager
def _joined_viewer(share_token: str, target_language: str = "fr"):
    with client.websocket_connect("/ws/view") as ws:
        ws.send_json({"type": "join_live", "share_token": share_token, "target_language": target_language})
        joined = ws.receive_json()
        assert joined["type"] == "live_joined"
        yield ws, joined


def test_join_live_with_a_known_token_returns_room_state_and_lines():
    share_token, room = _make_room(
        state="paused",
        lines=[{"index": 0, "original_text": "hola", "translations": {"fr": "salut"}}],
    )

    with client.websocket_connect("/ws/view") as ws:
        ws.send_json({"type": "join_live", "share_token": share_token, "target_language": "fr"})
        assert ws.receive_json() == {
            "type": "live_joined",
            "title": "Standup",
            "source_language": "en",
            "target_language": "fr",
            "state": "paused",
            "lines": [{"index": 0, "original_text": "hola", "translated_text": "salut"}],
        }


def test_join_live_translates_missing_lines_for_the_requested_language():
    share_token, room = _make_room(lines=[{"index": 0, "original_text": "hola"}])

    with client.websocket_connect("/ws/view") as ws:
        ws.send_json({"type": "join_live", "share_token": share_token, "target_language": "de"})
        joined = ws.receive_json()
        assert joined["lines"] == [{"index": 0, "original_text": "hola", "translated_text": "[de] hola"}]


def test_join_live_registers_the_connection_as_a_room_viewer():
    share_token, room = _make_room()

    with _joined_viewer(share_token):
        assert len(room.viewers) == 1


def test_disconnecting_removes_the_viewer_from_the_room():
    share_token, room = _make_room()

    with _joined_viewer(share_token):
        assert len(room.viewers) == 1

    assert len(room.viewers) == 0


def test_join_live_with_an_unknown_token_is_rejected_and_closed():
    with client.websocket_connect("/ws/view") as ws:
        ws.send_json({"type": "join_live", "share_token": str(uuid.uuid4()), "target_language": "fr"})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == viewer_ws_module.LIVE_NOT_AVAILABLE_CLOSE_CODE


def test_join_live_with_an_unsupported_language_is_rejected_and_closed():
    share_token, _room = _make_room()

    with client.websocket_connect("/ws/view") as ws:
        ws.send_json({"type": "join_live", "share_token": share_token, "target_language": "xx"})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == viewer_ws_module.LIVE_NOT_AVAILABLE_CLOSE_CODE


def test_a_non_join_live_first_message_is_rejected_and_closed():
    with client.websocket_connect("/ws/view") as ws:
        ws.send_json({"type": "set_viewer_language", "target_language": "fr"})
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == viewer_ws_module.LIVE_NOT_AVAILABLE_CLOSE_CODE


def test_invalid_json_as_the_first_message_is_rejected_and_closed():
    with client.websocket_connect("/ws/view") as ws:
        ws.send_text("not json")
        error = ws.receive_json()
        assert error["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == viewer_ws_module.LIVE_NOT_AVAILABLE_CLOSE_CODE


def test_set_viewer_language_replaces_the_whole_line_list_in_the_new_language():
    share_token, room = _make_room(
        lines=[
            {"index": 0, "original_text": "hola", "translations": {"fr": "salut"}},
            {"index": 1, "original_text": "mundo", "translations": {"fr": "monde"}},
        ]
    )

    with _joined_viewer(share_token, "fr") as (ws, _joined):
        ws.send_json({"type": "set_viewer_language", "target_language": "de"})
        assert ws.receive_json() == {
            "type": "live_lines_retranslated",
            "target_language": "de",
            "lines": [
                {"index": 0, "original_text": "hola", "translated_text": "[de] hola"},
                {"index": 1, "original_text": "mundo", "translated_text": "[de] mundo"},
            ],
        }


def test_set_viewer_language_updates_the_room_viewer_record():
    share_token, room = _make_room()

    with _joined_viewer(share_token, "fr") as (ws, _joined):
        [viewer_id] = list(room.viewers.keys())
        ws.send_json({"type": "set_viewer_language", "target_language": "de"})
        ws.receive_json()
        assert room.viewers[viewer_id][1] == "de"


def test_set_viewer_language_with_an_unsupported_code_returns_an_error_without_closing():
    share_token, _room = _make_room()

    with _joined_viewer(share_token, "fr") as (ws, _joined):
        ws.send_json({"type": "set_viewer_language", "target_language": "xx"})
        error = ws.receive_json()
        assert error["type"] == "error"
        # Still open - a follow-up message gets a normal response.
        ws.send_json({"type": "set_viewer_language", "target_language": "de"})
        assert ws.receive_json()["type"] == "live_lines_retranslated"


def test_request_audio_before_tts_lands_returns_audio_failed():
    share_token, _room = _make_room()

    with _joined_viewer(share_token, "fr") as (ws, _joined):
        ws.send_json({"type": "request_audio", "index": 0})
        assert ws.receive_json() == {
            "type": "audio_failed",
            "index": 0,
            "message": "Audio playback isn't available yet",
        }


def test_unknown_message_type_returns_an_error_without_closing():
    share_token, _room = _make_room()

    with _joined_viewer(share_token, "fr") as (ws, _joined):
        ws.send_json({"type": "something_else"})
        error = ws.receive_json()
        assert error["type"] == "error"
        ws.send_json({"type": "set_viewer_language", "target_language": "de"})
        assert ws.receive_json()["type"] == "live_lines_retranslated"


