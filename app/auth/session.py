"""Resolve the logged-in user for dashboard (/me) endpoints.

Real world:
- User signs in (Google, email/password) → API issues JWT access token.
- Client sends `Authorization: Bearer <jwt>` on every request.
- This module validates JWT `sub` claim → user_id.

Until login is built, supported paths:
1. Bearer token in secrets with `user_id` + `type: "user"`.
2. Development only: `X-User-Id` header when ENVIRONMENT=development.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth.bearer import validate_bearer_token
from app.auth.rate_limit import check_rate_limit
from app.config import get_settings

bearer_for_user = HTTPBearer(auto_error=False)


class UserSession(BaseModel):
    user_id: uuid.UUID
    token_id: str
    auth_method: Literal["bearer_static", "jwt"] = "bearer_static"


def _decode_user_id_from_jwt(token: str) -> uuid.UUID | None:
    settings = get_settings()
    if not settings.jwt_secret or token.count(".") != 2:
        return None
    try:
        import jwt

        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        sub = payload.get("sub")
        if sub:
            return uuid.UUID(str(sub))
    except Exception:
        return None
    return None


async def require_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_for_user),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> UserSession:
    settings = get_settings()

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization required. Send Bearer token from user login.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwt_user = _decode_user_id_from_jwt(token)
    if jwt_user is not None:
        return UserSession(user_id=jwt_user, token_id="jwt", auth_method="jwt")

    entry = validate_bearer_token(token)
    if entry is not None and entry.user_id:
        return UserSession(
            user_id=uuid.UUID(entry.user_id),
            token_id=entry.id,
            auth_method="bearer_static",
        )

    if settings.allow_dev_user_id_header and settings.environment == "development" and x_user_id:
        try:
            return UserSession(
                user_id=uuid.UUID(x_user_id),
                token_id="dev-header",
                auth_method="bearer_static",
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-User-Id") from exc

    if entry is not None and entry.token_type == "service":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Service API token cannot access user dashboard. "
                "Use a user session token (user_id in bearer_tokens) or JWT after login."
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or non-user bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_current_user_and_rate_limit(
    session: UserSession = Depends(require_current_user),
) -> UserSession:
    from app.auth.base import AuthContext

    check_rate_limit(
        AuthContext(
            subject_id=f"user:{session.user_id}",
            token_id=session.token_id,
            auth_method=session.auth_method,
        )
    )
    return session
