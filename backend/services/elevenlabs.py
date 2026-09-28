async def transcribe(audio_path: str) -> str:
    raise NotImplementedError("STT wired up in Phase 1")


async def synthesize(text: str) -> bytes:
    raise NotImplementedError("TTS wired up in Phase 4")
