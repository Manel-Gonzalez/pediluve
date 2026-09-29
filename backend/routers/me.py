import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from models.auth import CurrentUser
from services.auth import AuthenticatedUser, AuthError, AuthServiceUnavailable, verify_access_token

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ")
    try:
        return await verify_access_token(token)
    except AuthError as exc:
        # Generic detail: the raw exception may carry internal client/library
        # text that shouldn't reach an unauthenticated caller.
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc
    except AuthServiceUnavailable as exc:
        logger.exception("Could not verify access token")
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc


@router.get("/me")
async def me(current_user: AuthenticatedUser = Depends(get_current_user)) -> CurrentUser:
    return CurrentUser(id=current_user.id, email=current_user.email)
