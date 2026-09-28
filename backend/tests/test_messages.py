import pytest
from pydantic import ValidationError

from models.messages import ClientMessage, ErrorMessage, StartTranscription


def test_client_message_requires_text():
    with pytest.raises(ValidationError):
        ClientMessage.model_validate({"type": "message"})


def test_client_message_defaults_type():
    message = ClientMessage.model_validate({"text": "hi"})
    assert message.type == "message"
    assert message.text == "hi"


def test_start_transcription_defaults_audio_format():
    message = StartTranscription.model_validate({})
    assert message.audio_format == "pcm_16000"


def test_start_transcription_accepts_explicit_audio_format():
    message = StartTranscription.model_validate({"audio_format": "pcm_48000"})
    assert message.audio_format == "pcm_48000"


def test_error_message_shape():
    message = ErrorMessage(message="boom")
    assert message.model_dump() == {"type": "error", "message": "boom"}
