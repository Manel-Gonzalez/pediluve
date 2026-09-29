from typing import Literal

from pydantic import BaseModel


class ClientMessage(BaseModel):
    type: Literal["message"] = "message"
    text: str


class StartTranscription(BaseModel):
    type: Literal["start_transcription"] = "start_transcription"
    audio_format: str = "pcm_16000"
    # None = auto-detect (today's behavior). Fixed for the session once recording
    # starts - see docs/decisions.md for why changing it requires a stop/start.
    source_language: str | None = None


class StopTranscription(BaseModel):
    type: Literal["stop_transcription"] = "stop_transcription"


class SetTargetLanguage(BaseModel):
    type: Literal["set_target_language"] = "set_target_language"
    target_language: str


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
