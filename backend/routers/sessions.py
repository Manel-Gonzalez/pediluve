import logging
import re
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from models.sessions import (
    AddGuestRequest,
    MessageTranslation,
    SessionCreate,
    SessionDetail,
    SessionListResponse,
    SessionSummary,
    SessionUpdate,
    TranslateRequest,
    TranslateResponse,
)
from routers.me import get_current_user
from services import deepl, storage, supabase
from services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

MAX_LIST_LIMIT = 100


def _validate_uuid(session_id: str) -> None:
    # A malformed id can never match a real row, but letting it reach
    # Postgres would surface as a raw driver error (500) instead of the 404
    # every other "not found" path returns - checked here so all three cases
    # (bad UUID, unknown id, someone else's id under RLS) look the same to
    # the caller.
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found") from None


async def _message_count(user: AuthenticatedUser, session_id: str) -> int:
    detail = await supabase.get_session_with_messages(user, session_id)
    return len(detail["messages"]) if detail else 0


@router.post("/sessions", status_code=201, response_model=SessionSummary)
async def create_session(
    request: SessionCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SessionSummary:
    row = await supabase.create_session(current_user, title=request.title)
    return SessionSummary(**row, message_count=0)


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(default=20, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SessionListResponse:
    limit = min(limit, MAX_LIST_LIMIT)
    rows, has_more, total = await supabase.list_sessions(current_user, limit=limit, offset=offset)
    return SessionListResponse(
        items=[SessionSummary(**row) for row in rows], has_more=has_more, total=total
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SessionDetail:
    _validate_uuid(session_id)
    row = await supabase.get_session_with_messages(current_user, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetail(**row, message_count=len(row["messages"]))


@router.patch("/sessions/{session_id}", response_model=SessionSummary)
async def rename_session(
    session_id: str,
    request: SessionUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SessionSummary:
    _validate_uuid(session_id)
    row = await supabase.rename_session(current_user, session_id, request.title)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    message_count = await _message_count(current_user, session_id)
    return SessionSummary(**row, message_count=message_count)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    _validate_uuid(session_id)
    # Before the DB delete, not after: message_audio's own rows disappear
    # via the FK cascade regardless, but Storage objects aren't part of that
    # cascade - doing this first means a failure here leaves the session
    # (and the cached audio) intact for a retry, rather than an
    # unrecoverable orphan with no DB row left pointing at it. Best-effort:
    # a Storage hiccup must not block deleting the session itself.
    try:
        await storage.delete_session_audio(current_user, current_user.id, session_id)
    except Exception:
        logger.exception("Could not delete cached audio for session %s", session_id)

    deleted = await supabase.delete_session(current_user, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/shared/guest", status_code=201, response_model=SessionSummary)
async def add_guest(
    request: AddGuestRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SessionSummary:
    # A bad/unknown token and any other RPC failure (see migration 008's
    # add_session_guest) look the same from here - "not found" either way,
    # same reasoning as every other share-token-or-session-id lookup in
    # this file.
    try:
        await supabase.add_session_guest(current_user, request.share_token, request.target_language)
    except Exception:
        raise HTTPException(status_code=404, detail="Session not found") from None

    row = await supabase.get_session_by_share_token(current_user, request.share_token)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionSummary(**row)


@router.delete("/sessions/{session_id}/guest", status_code=204)
async def remove_guest(
    session_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    _validate_uuid(session_id)
    removed = await supabase.remove_session_guest(current_user, session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Not a guest of this session")


@router.post("/sessions/{session_id}/translate", response_model=TranslateResponse)
async def translate_session(
    session_id: str,
    request: TranslateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> TranslateResponse:
    # Re-translates a stored session to a different language for viewing -
    # nothing is written. The original live-session translation in
    # messages.translated_text/target_language is untouched.
    _validate_uuid(session_id)
    if request.target_language not in deepl.SUPPORTED_TARGET_LANGUAGES:
        raise HTTPException(
            status_code=400, detail=f"Unsupported target language: {request.target_language}"
        )

    row = await supabase.get_session_with_messages(current_user, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = row["messages"]
    translated_texts = (
        await deepl.translate_many(
            [message["original_text"] for message in messages], request.target_language
        )
        if messages
        else []
    )
    return TranslateResponse(
        target_language=request.target_language,
        translations=[
            MessageTranslation(message_id=message["id"], translated_text=translated_text)
            for message, translated_text in zip(messages, translated_texts)
        ],
    )


def _transcript_filename(title: str | None, target_language: str | None) -> str:
    name = title or "session"
    if target_language is not None:
        name = f"{name} ({target_language})"
    return f"{name}.txt"


def _content_disposition(filename: str) -> str:
    # RFC 5987: filename* carries the real (possibly non-ASCII) name,
    # percent-encoded (quote() already escapes CR/LF/quotes there, nothing
    # more needed); filename= stays a plain-ASCII fallback for clients that
    # don't understand filename* at all - a title with no non-ASCII
    # characters makes the two identical.
    #
    # SessionTitle's own validator only trims leading/trailing whitespace,
    # so a title carrying an embedded CR/LF or a bare `"` (still valid
    # ASCII) would otherwise land unescaped inside a quoted header value -
    # stripped here rather than at the model layer, since a title is only
    # dangerous in this one HTTP-header context, nowhere else it's used.
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii")
    ascii_fallback = re.sub(r'[\r\n"]', "", ascii_fallback) or "transcript.txt"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


def _format_transcript(messages: list[dict], translated_texts: list[str | None]) -> str:
    lines: list[str] = []
    for message, translated_text in zip(messages, translated_texts):
        lines.append(message["original_text"])
        if translated_text:
            lines.append(f"→ {translated_text}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


@router.get("/sessions/{session_id}/transcript")
async def download_transcript(
    session_id: str,
    target_language: str | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Response:
    # Plain-text download of a stored session's transcript - re-translated
    # to target_language on demand (nothing written, same as POST .../
    # translate) if given, otherwise each message's own stored
    # translated_text (the original live-session translation).
    _validate_uuid(session_id)
    if target_language is not None and target_language not in deepl.SUPPORTED_TARGET_LANGUAGES:
        raise HTTPException(
            status_code=400, detail=f"Unsupported target language: {target_language}"
        )

    row = await supabase.get_session_with_messages(current_user, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = row["messages"]
    if target_language is not None:
        translated_texts = (
            await deepl.translate_many(
                [message["original_text"] for message in messages], target_language
            )
            if messages
            else []
        )
    else:
        translated_texts = [message["translated_text"] for message in messages]

    return Response(
        content=_format_transcript(messages, translated_texts),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": _content_disposition(
                _transcript_filename(row["title"], target_language)
            )
        },
    )
