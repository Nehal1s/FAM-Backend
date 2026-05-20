from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import EmailStr
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_correlation_id, require_auth_and_rate_limit
from app.auth.base import AuthContext
from app.config import get_settings
from app.db.models import User, LawyerContract
from app.db.query import query
from app.exceptions import DbTimeoutError
from app.metrics.cloudwatch import LatencyTimer, record_error
from app.schemas.user import (
    ServiceSubscribeRequest,
    SubscriptionResponse,
    UserCreateRequest,
    UserEmailLookupResponse,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from app.services.lawyer import build_lawyer_artifact, get_active_lawyer_by_user
from app.services.subscription import subscribe_user_to_service
from app.services.users import get_user_or_404

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/users", tags=["users"])

MAX_PAGE_SIZE = 100
IDEMPOTENCY_KEY_MAX = 128


@router.get("", response_model=UserListResponse)
async def list_users(
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> UserListResponse:
    settings = get_settings()
    offset = (page - 1) * page_size

    with LatencyTimer("EndpointLatency", {"Endpoint": "list_users"}):
        logger.info("list_users_start", subject_id=auth.subject_id, page=page, page_size=page_size)

        async def _list(session: AsyncSession) -> tuple[int, list[User]]:
            active = User.deleted_at.is_(None)
            total = (
                await session.execute(select(func.count()).select_from(User).where(active))
            ).scalar_one()
            result = await session.execute(
                select(User)
                .where(active)
                .order_by(User.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            rows = list(result.scalars().all())
            return int(total), rows

        try:
            total, items = await query(
                _list,
                timeout_ms=settings.db_query_timeout_ms,
                operation="list_users",
            )
        except DbTimeoutError as exc:
            record_error("DbTimeout", {"Endpoint": "list_users"})
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Database query timed out",
            ) from exc

        return UserListResponse(
            items=[UserResponse.model_validate(u) for u in items],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.post("", response_model=UserResponse)
async def create_user(
    body: UserCreateRequest,
    response: Response,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> UserResponse:
    settings = get_settings()
    key = (idempotency_key or "").strip()[:IDEMPOTENCY_KEY_MAX] or None

    with LatencyTimer("EndpointLatency", {"Endpoint": "create_user"}):
        logger.info("create_user_start", subject_id=auth.subject_id, email=body.email)

        async def _create(session: AsyncSession) -> tuple[User, bool]:
            if key:
                existing = (
                    await session.execute(
                        select(User).where(User.idempotency_key == key, User.deleted_at.is_(None))
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return existing, True

            new_user = User(
                id=uuid.uuid4(),
                email=str(body.email).lower(),
                auth_method=body.auth_method.value,
                display_name=body.display_name,
                idempotency_key=key,
            )
            session.add(new_user)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                if key:
                    replay = (
                        await session.execute(
                            select(User).where(User.idempotency_key == key, User.deleted_at.is_(None))
                        )
                    ).scalar_one_or_none()
                    if replay is not None:
                        return replay, True
                raise
            await session.refresh(new_user)
            return new_user, False

        try:
            user, replay = await query(
                _create,
                timeout_ms=settings.db_query_timeout_ms,
                operation="create_user",
            )
        except DbTimeoutError as exc:
            record_error("DbTimeout", {"Endpoint": "create_user"})
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Database query timed out",
            ) from exc
        except IntegrityError as exc:
            record_error("DbConflict", {"Endpoint": "create_user"})
            logger.info("create_user_conflict", email=body.email)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email or idempotency key already exists",
            ) from exc

        if replay:
            logger.info("create_user_idempotent_replay", user_id=str(user.id))
            response.status_code = status.HTTP_200_OK
        else:
            logger.info("create_user_success", user_id=str(user.id))
            response.status_code = status.HTTP_201_CREATED

        return UserResponse.model_validate(user)


@router.get("/lookup", response_model=UserEmailLookupResponse)
async def lookup_user_by_email(
    email: Annotated[EmailStr, Query(description="Email to check")],
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> UserEmailLookupResponse:
    """Return whether a non-deleted user exists for this email (case-insensitive)."""
    settings = get_settings()
    normalized = email.strip().lower()

    with LatencyTimer("EndpointLatency", {"Endpoint": "lookup_user_by_email"}):
        logger.info("lookup_user_by_email_start", subject_id=auth.subject_id)

        async def _lookup(session: AsyncSession) -> bool:
            result = await session.execute(
                select(func.count())
                .select_from(User)
                .where(
                    func.lower(User.email) == normalized,
                    User.deleted_at.is_(None),
                )
            )
            return int(result.scalar_one()) > 0

        try:
            exists = await query(
                _lookup,
                timeout_ms=settings.db_query_timeout_ms,
                operation="lookup_user_by_email",
            )
        except DbTimeoutError as exc:
            record_error("DbTimeout", {"Endpoint": "lookup_user_by_email"})
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Database query timed out",
            ) from exc

        return UserEmailLookupResponse(exists=exists)


@router.patch("/{user_id}", response_model=UserResponse)
async def patch_user(
    user_id: uuid.UUID,
    body: UserPatchRequest,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> UserResponse:
    settings = get_settings()

    with LatencyTimer("EndpointLatency", {"Endpoint": "patch_user"}):
        logger.info("patch_user_start", user_id=str(user_id), subject_id=auth.subject_id)

        async def _patch(session: AsyncSession) -> User | None:
            result = await session.execute(
                select(User).where(User.id == user_id, User.deleted_at.is_(None))
            )
            user = result.scalar_one_or_none()
            if user is None:
                return None
            if body.display_name is not None:
                user.display_name = body.display_name
            if body.auth_method is not None:
                user.auth_method = body.auth_method.value
            await session.commit()
            await session.refresh(user)
            return user

        try:
            user = await query(
                _patch,
                timeout_ms=settings.db_query_timeout_ms,
                operation="patch_user",
            )
        except DbTimeoutError as exc:
            record_error("DbTimeout", {"Endpoint": "patch_user"})
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Database query timed out",
            ) from exc

        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        logger.info("patch_user_success", user_id=str(user_id))
        return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> UserResponse:
    settings = get_settings()

    with LatencyTimer("EndpointLatency", {"Endpoint": "get_user"}):
        logger.info(
            "get_user_start",
            user_id=str(user_id),
            subject_id=auth.subject_id,
        )

        async def _fetch(session: AsyncSession) -> UserResponse | None:
            result = await session.execute(
                select(User).where(User.id == user_id, User.deleted_at.is_(None))
            )
            user = result.scalar_one_or_none()
            if user is None:
                return None
            lawyer = await get_active_lawyer_by_user(session, user_id)
            artifact = build_lawyer_artifact(lawyer) if lawyer else None
            base = UserResponse.model_validate(user)
            return base.model_copy(update={"lawyer": artifact})

        try:
            response = await query(
                _fetch,
                timeout_ms=settings.db_query_timeout_ms,
                operation="get_user",
            )
        except DbTimeoutError as exc:
            record_error("DbTimeout", {"Endpoint": "get_user"})
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Database query timed out",
            ) from exc

        if response is None:
            logger.info("get_user_not_found", user_id=str(user_id))
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        logger.info("get_user_success", user_id=str(user_id))
        return response


# Subscribe to a service
@router.post("/{user_id}/subscribe", response_model=UserResponse)
async def subscribe_to_service(
    user_id: uuid.UUID,
    body: ServiceSubscribeRequest,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> UserResponse:
    settings = get_settings()

    with LatencyTimer("EndpointLatency", {"Endpoint": "subscribe_to_service"}):
        logger.info("subscribe_to_service_start", user_id=str(user_id), service_type=body.service_type, subject_id=auth.subject_id)

        async def _subscribe(session: AsyncSession) -> UserResponse:
            user = await get_user_or_404(session, user_id)

            if body.service_type == "lawyer":
                if not body.service_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="service_id is required for lawyer subscriptions")

                lawyer = await get_active_lawyer_by_user(session, body.service_id)
                if lawyer is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lawyer not found")

                contract = LawyerContract(
                    lawyer_id=body.service_id,
                    client_user_id=user_id,
                    title=body.title,
                    description=body.description,
                    status="pending",
                )
                session.add(contract)
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown service type: {body.service_type}")

            await session.commit()
            return UserResponse.model_validate(user)

        try:
            response = await query(
                _subscribe,
                timeout_ms=settings.db_query_timeout_ms,
                operation="subscribe_to_service",
            )
        except DbTimeoutError as exc:
            record_error("DbTimeout", {"Endpoint": "subscribe_to_service"})
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Database query timed out",
            ) from exc
        except IntegrityError as exc:
            record_error("DbConflict", {"Endpoint": "subscribe_to_service"})
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already subscribed to this service",
            ) from exc

        logger.info("subscribe_to_service_success", user_id=str(user_id))
        return response