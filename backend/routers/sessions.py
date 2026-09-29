import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from models.sessions import SessionCreate, SessionDetail, SessionListResponse, SessionSummary, SessionUpdate
from routers.me import get_current_user
from services import supabase
from services.auth import AuthenticatedUser

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
    rows, has_more = await supabase.list_sessions(current_user, limit=limit, offset=offset)
    return SessionListResponse(items=[SessionSummary(**row) for row in rows], has_more=has_more)


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
    deleted = await supabase.delete_session(current_user, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
