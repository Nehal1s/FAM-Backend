"""Logged-in user dashboard (GET /me/profile)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_correlation_id
from app.auth.session import UserSession, require_current_user_and_rate_limit
from app.config import get_settings
from app.db.query import query
from app.exceptions import DbTimeoutError
from app.metrics.cloudwatch import LatencyTimer, record_error
from app.schemas.profile import UserProfileDashboard
from app.services.profile import build_user_profile

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/me", tags=["profile"])


@router.get("/profile", response_model=UserProfileDashboard)
async def get_my_profile(
    session: UserSession = Depends(require_current_user_and_rate_limit),
    # correlation_id: str = Depends(get_correlation_id),
) -> UserProfileDashboard:
    """Dashboard for the logged-in user: account, services they provide, services they use."""
    settings = get_settings()

    with LatencyTimer("EndpointLatency", {"Endpoint": "get_my_profile"}):
        logger.info("get_my_profile_start", user_id=str(session.user_id))

        async def _load(db: AsyncSession) -> UserProfileDashboard | None:
            return await build_user_profile(db, session.user_id)

        try:
            profile = await query(
                _load,
                timeout_ms=settings.db_query_timeout_ms,
                operation="get_my_profile",
            )
        except DbTimeoutError as exc:
            record_error("DbTimeout", {"Endpoint": "get_my_profile"})
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Database query timed out",
            ) from exc

        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        logger.info(
            "get_my_profile_success",
            user_id=str(session.user_id),
            providing=len(profile.services_providing),
            using=len(profile.services_using),
        )
        return profile
