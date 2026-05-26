from __future__ import annotations

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password, verify_password
from app.config import get_settings
from app.db.models import User
from app.db.query import query
from app.exceptions import DbTimeoutError

logger = structlog.get_logger(__name__)


# ── Signup ────────────────────────────────────────────────────────────────────

async def signup_with_email(
    email: str,
    password: str,
    display_name: str | None,
) -> User:
    """Create a new email+password user. Raises 409 if email already exists."""

    # 1. Check for existing active user
    async def _find(session: AsyncSession):
        result = await session.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    settings = get_settings()
    try:
        existing = await query(_find, timeout_ms=settings.db_query_timeout_ms, operation="signup_check_email")
    except DbTimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Database query timed out")

    if existing:
        logger.warning("signup_email_conflict", email=email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # 2. Create user
    async def _create(session: AsyncSession):
        user = User(
            email=email,
            display_name=display_name,
            auth_method="email_password",
            hashed_password=hash_password(password),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    try:
        user = await query(_create, timeout_ms=settings.db_query_timeout_ms, operation="signup_create_user")
    except DbTimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Database query timed out")

    logger.info("signup_success", user_id=str(user.id), auth_method="email_password")
    return user


# ── Login ─────────────────────────────────────────────────────────────────────

async def login_with_email(email: str, password: str) -> User:
    """Verify credentials. Raises 401 on any failure (no email enumeration)."""

    async def _find(session: AsyncSession):
        result = await session.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    settings = get_settings()
    try:
        user = await query(_find, timeout_ms=settings.db_query_timeout_ms, operation="login_find_user")
    except DbTimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Database query timed out")

    # Deliberately use the same error for "not found" and "wrong password"
    # to prevent email enumeration attacks
    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
    )

    if user is None:
        logger.warning("login_user_not_found", email=email)
        raise invalid_exc

    if user.auth_method != "email_password" or not user.hashed_password:
        # User exists but signed up via Google — give a helpful nudge
        logger.warning("login_wrong_auth_method", user_id=str(user.id), auth_method=user.auth_method)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This account uses {user.auth_method} login. Please use that method instead.",
        )

    if not verify_password(password, user.hashed_password):
        logger.warning("login_wrong_password", user_id=str(user.id))
        raise invalid_exc

    logger.info("login_success", user_id=str(user.id))
    return user


# ── Google OAuth upsert (moved here from users.py) ────────────────────────────

async def get_or_create_google_user(
    email: str,
    display_name: str | None,
    google_sub: str,
) -> User:
    async def _find(session: AsyncSession):
        result = await session.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    settings = get_settings()
    try:
        user = await query(_find, timeout_ms=settings.db_query_timeout_ms, operation="google_find_user")
    except DbTimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Database query timed out")

    if user:
        if user.auth_method != "google":
            # Account exists via email+password — block silent takeover
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Please log in with email and password.",
            )
        return user

    async def _create(session: AsyncSession):
        new_user = User(
            email=email,
            display_name=display_name,
            auth_method="google",
            idempotency_key=f"google:{google_sub}",
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        return new_user

    try:
        return await query(_create, timeout_ms=settings.db_query_timeout_ms, operation="google_create_user")
    except DbTimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Database query timed out")