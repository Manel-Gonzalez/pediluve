import secrets
import time
from collections import OrderedDict
from collections.abc import Callable

# KAN-87: freshly synthesized audio, held just long enough to be played.
# A cache miss used to wait for the Storage upload, the message_audio row
# and a signed URL before a listener could start; now it answers as soon
# as ElevenLabs returns, with a URL served from here, and tts_cache does
# the caching in the background. Same lifetime as a signed URL.
TTL_SECONDS = 60 * 60
MAX_ENTRIES = 500  # a few MB of short mp3 clips


class LiveAudioStore:
    def __init__(
        self,
        ttl_seconds: float = TTL_SECONDS,
        max_entries: int = MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        # Insertion order is age order, so the oldest is always first.
        self._clips: OrderedDict[str, tuple[float, bytes]] = OrderedDict()

    def put(self, audio: bytes) -> str:
        # Unguessable, like a signed URL's token: this is all that protects
        # the clip, the same as a share link protects its live session.
        token = secrets.token_urlsafe(32)
        self._clips[token] = (self._clock() + self._ttl, audio)
        while len(self._clips) > self._max:
            self._clips.popitem(last=False)
        return token

    def get(self, token: str) -> bytes | None:
        entry = self._clips.get(token)
        if entry is None:
            return None
        expires_at, audio = entry
        if self._clock() >= expires_at:
            del self._clips[token]
            return None
        return audio


store = LiveAudioStore()


def live_audio_url(token: str) -> str:
    # Relative on purpose: the page resolves it against its own origin, so
    # it goes through the Vite proxy on localhost, the LAN and a tunnel
    # alike (KAN-66).
    return f"/api/live-audio/{token}"
