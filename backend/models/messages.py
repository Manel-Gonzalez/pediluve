from typing import Literal

from pydantic import BaseModel


class ClientMessage(BaseModel):
    type: Literal["message"] = "message"
    text: str


class StartTranscription(BaseModel):
    type: Literal["start_transcription"] = "start_transcription"
    audio_format: str = "pcm_16000"


class StopTranscription(BaseModel):
    type: Literal["stop_transcription"] = "stop_transcription"


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
    text: str
