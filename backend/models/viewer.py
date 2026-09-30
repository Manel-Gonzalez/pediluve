from typing import Literal

from pydantic import BaseModel

# Message models for /ws/view (KAN-50/KAN-55) - the anonymous, read-only
# counterpart to routers/ws.py's owner protocol (models/messages.py). Kept
# in a separate module, matching the separate-handler design: a viewer's
# messages never need to overlap with an owner's (see docs/decisions.md D1).


class JoinLive(BaseModel):
    # Must be the first message on the connection - the share_token is the
    # viewer's only credential (see docs/decisions.md D2 for why it's sent
    # here rather than in the WS URL, same reasoning as owner /ws's
    # authenticate/join_session).
    type: Literal["join_live"] = "join_live"
    share_token: str
    target_language: str


class SetViewerLanguage(BaseModel):
    type: Literal["set_viewer_language"] = "set_viewer_language"
    target_language: str


class RequestAudio(BaseModel):
    type: Literal["request_audio"] = "request_audio"
    index: int


class LiveLineOut(BaseModel):
    index: int
    original_text: str
    translated_text: str | None = None


class LiveJoined(BaseModel):
    # Reply to a successful join_live: the room's current metadata plus
    # every line published so far, translated to the requested language.
    type: Literal["live_joined"] = "live_joined"
    title: str | None
    source_language: str | None
    target_language: str
    state: str
    lines: list[LiveLineOut]


class LiveLine(BaseModel):
    type: Literal["live_line"] = "live_line"
    index: int
    original_text: str
    translated_text: str | None
    target_language: str


class LiveLinesRetranslated(BaseModel):
    # Sent after set_viewer_language - replaces the viewer's whole line list
    # rather than patching individual rows, mirroring owner /ws's
    # retranslated_transcripts.
    type: Literal["live_lines_retranslated"] = "live_lines_retranslated"
    target_language: str
    lines: list[LiveLineOut]


class LiveStatus(BaseModel):
    type: Literal["live_status"] = "live_status"
    state: str


class AudioReady(BaseModel):
    type: Literal["audio_ready"] = "audio_ready"
    index: int
    target_language: str
    audio_url: str
    cached: bool


class AudioFailed(BaseModel):
    type: Literal["audio_failed"] = "audio_failed"
    index: int
    message: str
