import re
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Response

from services import live_audio

router = APIRouter()

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _byte_range(header: str | None, size: int) -> tuple[int, int] | Literal["unsatisfiable"] | None:
    # (start, end) inclusive for a usable single range, None to serve the
    # whole clip (no header, or one we don't understand).
    match = _RANGE.match(header or "")
    if match is None or match.group(1) == match.group(2) == "":
        return None
    first, last = match.groups()
    if first == "":
        # "bytes=-N": the last N bytes.
        start, end = max(size - int(last), 0), size - 1
    else:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        return "unsatisfiable"
    return start, end


# KAN-87: anonymous, like /ws/view - the unguessable token is the only key
# (see services/live_audio.py). Range support because iOS Safari won't play
# media from a server that doesn't answer it with 206.
@router.get("/api/live-audio/{token}")
async def get_live_audio(token: str, range: str | None = Header(default=None)) -> Response:
    audio = live_audio.store.get(token)
    if audio is None:
        raise HTTPException(status_code=404, detail="Audio not found or expired")

    size = len(audio)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    byte_range = _byte_range(range, size)
    if byte_range == "unsatisfiable":
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
    if byte_range is None:
        return Response(content=audio, media_type="audio/mpeg", headers=headers)
    start, end = byte_range
    return Response(
        content=audio[start : end + 1],
        status_code=206,
        media_type="audio/mpeg",
        headers={**headers, "Content-Range": f"bytes {start}-{end}/{size}"},
    )
