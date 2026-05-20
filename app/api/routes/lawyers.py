from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_correlation_id, require_auth_and_rate_limit
from app.auth.base import AuthContext
from app.config import get_settings
from app.db.models import Lawyer, LawyerContract, User
from app.db.query import query
from app.exceptions import DbTimeoutError
from app.metrics.cloudwatch import LatencyTimer, record_error
from app.schemas.lawyer import (
    LawyerContractCreateRequest,
    LawyerContractResponse,
    LawyerContractUpdateRequest,
    LawyerPromoteRequest,
    LawyerResponse,
    LawyerUpdateRequest,
)
from app.services.lawyer import (
    build_lawyer_response,
    get_active_lawyer,
    get_active_lawyer_by_user,
    touch_lawyer_updated,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/lawyers", tags=["lawyers"])


async def _run_query(operation: str, fn):
    settings = get_settings()
    try:
        return await query(fn, timeout_ms=settings.db_query_timeout_ms, operation=operation)
    except DbTimeoutError as exc:
        record_error("DbTimeout", {"Endpoint": operation})
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Database query timed out",
        ) from exc


async def _get_user_or_404(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/promote", response_model=LawyerResponse, status_code=status.HTTP_201_CREATED)
async def promote_user_to_lawyer(
    body: LawyerPromoteRequest,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> LawyerResponse:
    with LatencyTimer("EndpointLatency", {"Endpoint": "promote_lawyer"}):
        logger.info("promote_lawyer_start", user_id=str(body.user_id), by=auth.subject_id)

        async def _promote(session: AsyncSession) -> LawyerResponse:
            await _get_user_or_404(session, body.user_id)
            existing = await get_active_lawyer_by_user(session, body.user_id)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User is already an active lawyer",
                )

            lawyer = Lawyer(
                user_id=body.user_id,
                service_type="lawyer",
                status="active",
                bar_number=body.bar_number,
                license_jurisdiction=body.license_jurisdiction,
                firm_name=body.firm_name,
                specializations=body.specializations,
                bio=body.bio,
                years_experience=body.years_experience,
                promoted_by=auth.subject_id,
            )
            session.add(lawyer)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not promote user to lawyer",
                ) from exc
            await session.refresh(lawyer)
            return await build_lawyer_response(session, lawyer)

        return await _run_query("promote_lawyer", _promote)


@router.get("", response_model=list[LawyerResponse])
async def list_lawyers(
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[str | None, Query(alias="status")] = "active",
) -> list[LawyerResponse]:
    offset = (page - 1) * page_size

    async def _list(session: AsyncSession) -> list[LawyerResponse]:
        q = select(Lawyer).where(Lawyer.deleted_at.is_(None))
        if status_filter:
            q = q.where(Lawyer.status == status_filter)
        q = q.order_by(Lawyer.promoted_at.desc()).offset(offset).limit(page_size)
        lawyers = list((await session.execute(q)).scalars().all())
        return [await build_lawyer_response(session, lw) for lw in lawyers]

    return await _run_query("list_lawyers", _list)


@router.get("/by-user/{user_id}", response_model=LawyerResponse)
async def get_lawyer_by_user(
    user_id: uuid.UUID,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> LawyerResponse:
    async def _fetch(session: AsyncSession) -> LawyerResponse:
        lawyer = await get_active_lawyer_by_user(session, user_id)
        if lawyer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lawyer not found for user")
        return await build_lawyer_response(session, lawyer)

    return await _run_query("get_lawyer_by_user", _fetch)


@router.get("/{lawyer_id}", response_model=LawyerResponse)
async def get_lawyer(
    lawyer_id: uuid.UUID,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> LawyerResponse:
    async def _fetch(session: AsyncSession) -> LawyerResponse:
        lawyer = await get_active_lawyer(session, lawyer_id)
        if lawyer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lawyer not found")
        return await build_lawyer_response(session, lawyer)

    return await _run_query("get_lawyer", _fetch)


@router.patch("/{lawyer_id}", response_model=LawyerResponse)
async def update_lawyer(
    lawyer_id: uuid.UUID,
    body: LawyerUpdateRequest,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> LawyerResponse:
    async def _update(session: AsyncSession) -> LawyerResponse:
        lawyer = await get_active_lawyer(session, lawyer_id)
        if lawyer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lawyer not found")

        updates = body.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(lawyer, field, value)
        touch_lawyer_updated(lawyer)
        await session.commit()
        await session.refresh(lawyer)
        return await build_lawyer_response(session, lawyer)

    return await _run_query("update_lawyer", _update)


@router.delete("/{lawyer_id}")
async def demote_lawyer(
    lawyer_id: uuid.UUID,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> dict[str, str]:
    """Soft-delete lawyer profile (demote). User account remains."""

    async def _demote(session: AsyncSession) -> dict[str, str]:
        lawyer = await get_active_lawyer(session, lawyer_id)
        if lawyer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lawyer not found")
        lawyer.status = "inactive"
        lawyer.deleted_at = datetime.now(timezone.utc)
        touch_lawyer_updated(lawyer)
        await session.commit()
        return {"status": "demoted", "lawyer_id": str(lawyer_id)}

    return await _run_query("demote_lawyer", _demote)


# --- Contracts (client subscribes to lawyer) ---


@router.post("/{lawyer_id}/contracts", response_model=LawyerContractResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    lawyer_id: uuid.UUID,
    body: LawyerContractCreateRequest,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> LawyerContractResponse:
    async def _create(session: AsyncSession) -> LawyerContractResponse:
        lawyer = await get_active_lawyer(session, lawyer_id)
        if lawyer is None or lawyer.status != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active lawyer not found")
        if body.client_user_id == lawyer.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lawyer cannot contract with themselves",
            )
        await _get_user_or_404(session, body.client_user_id)

        contract = LawyerContract(
            lawyer_id=lawyer_id,
            client_user_id=body.client_user_id,
            title=body.title,
            description=body.description,
            status="pending",
        )
        session.add(contract)
        await session.commit()
        await session.refresh(contract)
        return LawyerContractResponse.model_validate(contract)

    return await _run_query("create_lawyer_contract", _create)


@router.get("/{lawyer_id}/contracts", response_model=list[LawyerContractResponse])
async def list_lawyer_contracts(
    lawyer_id: uuid.UUID,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
    contract_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[LawyerContractResponse]:
    async def _list(session: AsyncSession) -> list[LawyerContractResponse]:
        lawyer = await get_active_lawyer(session, lawyer_id)
        if lawyer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lawyer not found")
        q = select(LawyerContract).where(LawyerContract.lawyer_id == lawyer_id)
        if contract_status:
            q = q.where(LawyerContract.status == contract_status)
        q = q.order_by(LawyerContract.created_at.desc())
        rows = list((await session.execute(q)).scalars().all())
        return [LawyerContractResponse.model_validate(c) for c in rows]

    return await _run_query("list_lawyer_contracts", _list)


@router.get("/contracts/by-client/{client_user_id}", response_model=list[LawyerContractResponse])
async def list_client_contracts(
    client_user_id: uuid.UUID,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> list[LawyerContractResponse]:
    async def _list(session: AsyncSession) -> list[LawyerContractResponse]:
        await _get_user_or_404(session, client_user_id)
        q = (
            select(LawyerContract)
            .where(LawyerContract.client_user_id == client_user_id)
            .order_by(LawyerContract.created_at.desc())
        )
        rows = list((await session.execute(q)).scalars().all())
        return [LawyerContractResponse.model_validate(c) for c in rows]

    return await _run_query("list_client_contracts", _list)


@router.patch("/contracts/{contract_id}", response_model=LawyerContractResponse)
async def update_contract(
    contract_id: uuid.UUID,
    body: LawyerContractUpdateRequest,
    auth: AuthContext = Depends(require_auth_and_rate_limit),
    correlation_id: str = Depends(get_correlation_id),
) -> LawyerContractResponse:
    async def _update(session: AsyncSession) -> LawyerContractResponse:
        contract = (
            await session.execute(select(LawyerContract).where(LawyerContract.id == contract_id))
        ).scalar_one_or_none()
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

        updates = body.model_dump(exclude_unset=True)
        new_status = updates.pop("status", None)
        if new_status:
            contract.status = new_status
            now = datetime.now(timezone.utc)
            if new_status == "active" and contract.started_at is None:
                contract.started_at = now
            if new_status in ("completed", "cancelled") and contract.ended_at is None:
                contract.ended_at = now
        for field, value in updates.items():
            setattr(contract, field, value)
        contract.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(contract)
        return LawyerContractResponse.model_validate(contract)

    return await _run_query("update_lawyer_contract", _update)
