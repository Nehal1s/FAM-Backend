from __future__ import annotations

import token
from typing import Literal

from jose import JWTError

from app.auth.jwt import decode_jwt
from app.config import Settings
from fastapi import Depends, HTTPException, Security, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth.bearer import validate_bearer_token

bearer_scheme = HTTPBearer(auto_error=False)
settings = Settings()


class AuthContext(BaseModel):
    subject_id: str
    token_id: str
    auth_method: Literal["bearer_static", "jwt"]


# async def require_auth(
#     credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
# ) -> AuthContext:
#     if credentials is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail=(
#                 "Authorization header required. "
#                 'Send: Authorization: Bearer <token> (token from BEARER_TOKENS_JSON or Secrets Manager)'
#             ),
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     if credentials.scheme.lower() != "bearer":
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Authorization scheme must be Bearer",
#             headers={"WWW-Authenticate": "Bearer"},
#         )

#     token = credentials.credentials
#     if not token:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Missing bearer token",
#             headers={"WWW-Authenticate": "Bearer"},
#         )

#     entry = validate_bearer_token(token)
#     if entry is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid bearer token",
#             headers={"WWW-Authenticate": "Bearer"},
#         )

#     return AuthContext(
#         subject_id=f"service:{entry.id}",
#         token_id=entry.id,
#         auth_method="bearer_static",
#     )

async def require_auth(request: Request) -> AuthContext:
    # Try cookie-based JWT first
    cookie_token = request.cookie.get(settings.cookie_name)
    if cookie_token:
        try:
            payload = decode_jwt(cookie_token)
            subject_id = payload["sub"]
            return AuthContext(
                subject_id = subject_id,
                token_id = subject_id,
                auth_method = "jwt",
            )
        except JWTError:
            # Cookie present but invalid/expired — don't fall through,
            # fail loudly so the client knows to re-authenticate
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid. Please log in again.",
            )
    
    # ── 2. Bearer token (service tokens / static dev tokens) ─────────────────
    auth_header = request.headers.get("Authorization", "")

    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authentication required. "
                "Send: Authorization: Bearer <token>, "
                "or authenticate via Google OAuth to receive a session cookie."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization scheme must be Bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = parts[1].strip()
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    entry = validate_bearer_token(raw_token)
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
