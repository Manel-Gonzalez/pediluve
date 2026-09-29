import pytest
from pydantic import ValidationError

from models.messages import (
    ClientMessage,
    ErrorMessage,
    SetTargetLanguage,
    StartTranscription,
    Transcript,
)


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


def test_start_transcription_defaults_source_language_to_none():
    message = StartTranscription.model_validate({})
    assert message.source_language is None


def test_start_transcription_accepts_an_explicit_source_language():
    message = StartTranscription.model_validate({"source_language": "es"})
    assert message.source_language == "es"


def test_set_target_language_requires_a_target_language():
    with pytest.raises(ValidationError):
        SetTargetLanguage.model_validate({})


def test_set_target_language_shape():
    message = SetTargetLanguage.model_validate({"target_language": "fr"})
    assert message.model_dump() == {"type": "set_target_language", "target_language": "fr"}


def test_transcript_defaults_translated_text_and_target_language_to_none():
    message = Transcript(original_text="hello")
    assert message.model_dump() == {
        "type": "transcript",
        "original_text": "hello",
        "translated_text": None,
        "target_language": None,
    }


def test_transcript_accepts_translated_text_and_target_language():
    message = Transcript(original_text="hello", translated_text="hola", target_language="es")
    assert message.model_dump() == {
        "type": "transcript",
        "original_text": "hello",
        "translated_text": "hola",
        "target_language": "es",
    }
