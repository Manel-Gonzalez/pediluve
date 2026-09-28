from typing import Literal

from pydantic import BaseModel


class ClientMessage(BaseModel):
    type: Literal["message"] = "message"
    text: str


class EchoMessage(BaseModel):
    type: Literal["echo"] = "echo"
    text: str


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str


class AudioChunkReceived(BaseModel):
    type: Literal["audio_chunk_received"] = "audio_chunk_received"
    bytes: int
