from __future__ import annotations

import structlog
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.auth.jwt import create_jwt
from app.config import get_settings
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest
from app.services.auth import get_or_create_google_user, login_with_email, signup_with_email

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

# ── Google OAuth setup ────────────────────────────────────────────────────────

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_auth_cookie(response: JSONResponse, user_id: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=create_jwt(user_id),
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.jwt_expire_minutes * 60,
    )


# ── Email + Password ──────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest):
    user = await signup_with_email(
        email=body.email,
        password=body.password,
        display_name=body.display_name,
    )

    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=AuthResponse(
            user_id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            auth_method=user.auth_method,
            message="Account created successfully",
        ).model_dump(),
    )
    _set_auth_cookie(response, str(user.id))
    return response


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    user = await login_with_email(email=body.email, password=body.password)

    response = JSONResponse(
        content=AuthResponse(
            user_id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            auth_method=user.auth_method,
            message="Logged in successfully",
        ).model_dump()
    )
    _set_auth_cookie(response, str(user.id))
    return response


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google/login")
async def google_login(request: Request):
    return await oauth.google.authorize_redirect(
        request,
        redirect_uri=settings.google_redirect_uri,
    )


@router.get("/google/callback")
async def google_callback(request: Request):
    try:
        google_token = await oauth.google.authorize_access_token(request)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google OAuth failed")

    user_info = google_token.get("userinfo")
    if not user_info or not user_info.get("email"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not retrieve email from Google")

    user = await get_or_create_google_user(
        email=user_info["email"],
        display_name=user_info.get("name"),
        google_sub=user_info["sub"],
    )

    response = JSONResponse(
        content=AuthResponse(
            user_id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            auth_method=user.auth_method,
            message="Logged in with Google successfully",
        ).model_dump()
    )
    _set_auth_cookie(response, str(user.id))
    return response


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout():
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(key=settings.cookie_name)
    return response