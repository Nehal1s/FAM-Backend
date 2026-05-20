from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth.bearer import validate_bearer_token

bearer_scheme = HTTPBearer(auto_error=False)


class AuthContext(BaseModel):
    subject_id: str
    token_id: str
    auth_method: Literal["bearer_static", "jwt"] = "bearer_static"


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> AuthContext:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authorization header required. "
                'Send: Authorization: Bearer <token> (token from BEARER_TOKENS_JSON or Secrets Manager)'
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization scheme must be Bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    entry = validate_bearer_token(token)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthContext(
        subject_id=f"service:{entry.id}",
        token_id=entry.id,
        auth_method="bearer_static",
    )
