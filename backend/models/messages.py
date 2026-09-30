from typing import Literal

from pydantic import BaseModel


class ClientMessage(BaseModel):
    type: Literal["message"] = "message"
    text: str


class Authenticate(BaseModel):
    # Must be the first text message on the connection; may be re-sent later
    # to swap in a refreshed access_token without reconnecting.
    type: Literal["authenticate"] = "authenticate"
    access_token: str


class StartTranscription(BaseModel):
    type: Literal["start_transcription"] = "start_transcription"
    audio_format: str = "pcm_16000"
    # None = auto-detect (today's behavior). Fixed for the session once recording
    # starts - see docs/decisions.md for why changing it requires a stop/start.
    source_language: str | None = None


class StopTranscription(BaseModel):
    type: Literal["stop_transcription"] = "stop_transcription"


class JoinSession(BaseModel):
    # Attaches this connection to an already-created session (created via the
    # REST API's POST /api/sessions) rather than the WS implicitly creating
    # one - required before start_transcription/set_target_language.
    type: Literal["join_session"] = "join_session"
    session_id: str


class SetTargetLanguage(BaseModel):
    type: Literal["set_target_language"] = "set_target_language"
    target_language: str


class Authenticated(BaseModel):
    type: Literal["authenticated"] = "authenticated"
    user_id: str


class EchoMessage(BaseModel):
    type: Literal["echo"] = "echo"
    text: str


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str


class PartialTranscript(BaseModel):
    type: Literal["partial_transcript"] = "partial_transcript"
    text: str


class Transcript(BaseModel):
    type: Literal["transcript"] = "transcript"
    original_text: str
    # Both null until a target language has ever been set; translated_text stays
    # null (target_language does not) if DeepL fails for this specific message.
    translated_text: str | None = None
    target_language: str | None = None


class SessionJoined(BaseModel):
    # Reply to a successful join_session: the session's current metadata plus
    # every transcript already stored, so a client re-attaching to an
    # existing session (a resume, or a second tab) can render its history
    # before anything new is said.
    type: Literal["session_joined"] = "session_joined"
    session_id: str
    title: str | None
    source_language: str | None
    target_language: str | None
    transcripts: list[Transcript]
    # The capability token for this session's QR/share link (KAN-50) - lets
    # the owner's live view render the Share panel without a separate fetch.
    share_token: str


class RetranslatedTranscripts(BaseModel):
    # Sent when the target language changes mid-session and there's already
    # committed transcript to retranslate - the client replaces its whole
    # transcript list with this one rather than matching individual rows, so
    # no per-message id/sequence needs to go over the wire for this.
    type: Literal["retranslated_transcripts"] = "retranslated_transcripts"
    target_language: str
    transcripts: list[Transcript]
