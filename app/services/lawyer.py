"""Lawyer domain helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Lawyer, LawyerContract
from app.schemas.lawyer import LawyerArtifact, LawyerResponse
from app.schemas.service import IndividualServiceType


async def get_active_lawyer(session: AsyncSession, lawyer_id: uuid.UUID) -> Lawyer | None:
    result = await session.execute(
        select(Lawyer)
        .where(Lawyer.id == lawyer_id, Lawyer.deleted_at.is_(None))
        .options(selectinload(Lawyer.contracts))
    )
    return result.scalar_one_or_none()


async def get_active_lawyer_by_user(session: AsyncSession, user_id: uuid.UUID) -> Lawyer | None:
    result = await session.execute(
        select(Lawyer)
        .where(Lawyer.user_id == user_id, Lawyer.deleted_at.is_(None))
        .options(selectinload(Lawyer.contracts))
    )
    return result.scalar_one_or_none()


async def get_lawyer_stats(session: AsyncSession, lawyer_id: uuid.UUID) -> tuple[float | None, int]:
    avg = (
        await session.execute(
            select(func.avg(LawyerContract.rating)).where(
                LawyerContract.lawyer_id == lawyer_id,
                LawyerContract.rating.is_not(None),
            )
        )
    ).scalar_one()
    count = (
        await session.execute(
            select(func.count()).select_from(LawyerContract).where(LawyerContract.lawyer_id == lawyer_id)
        )
    ).scalar_one()
    return (float(avg) if avg is not None else None, int(count or 0))


async def get_batch_lawyer_stats(
    session: AsyncSession, lawyer_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[float | None, int]]:
    """Get stats for multiple lawyers in batch (fixes N+1 query problem)."""
    if not lawyer_ids:
        return {}

    # Get average ratings for all lawyers in one query
    ratings_result = await session.execute(
        select(
            LawyerContract.lawyer_id,
            func.avg(LawyerContract.rating).label("avg_rating"),
        )
        .where(
            LawyerContract.lawyer_id.in_(lawyer_ids),
            LawyerContract.rating.is_not(None),
        )
        .group_by(LawyerContract.lawyer_id)
    )
    ratings_map = {row[0]: float(row[1]) if row[1] is not None else None for row in ratings_result}

    # Get contract counts for all lawyers in one query
    counts_result = await session.execute(
        select(
            LawyerContract.lawyer_id,
            func.count(LawyerContract.id).label("contract_count"),
        )
        .where(LawyerContract.lawyer_id.in_(lawyer_ids))
        .group_by(LawyerContract.lawyer_id)
    )
    counts_map = {row[0]: int(row[1]) for row in counts_result}

    # Combine results for all lawyer IDs (fill missing with defaults)
    return {
        lawyer_id: (ratings_map.get(lawyer_id), counts_map.get(lawyer_id, 0)) for lawyer_id in lawyer_ids
    }


def build_lawyer_artifact(lawyer: Lawyer) -> LawyerArtifact:
    return LawyerArtifact(
        lawyer_id=lawyer.id,
        service_type=IndividualServiceType(lawyer.service_type),
        status=lawyer.status,
        bar_number=lawyer.bar_number,
        license_jurisdiction=lawyer.license_jurisdiction,
        firm_name=lawyer.firm_name,
        specializations=lawyer.specializations,
    )


async def build_lawyer_response(session: AsyncSession, lawyer: Lawyer) -> LawyerResponse:
    avg_rating, contract_count = await get_lawyer_stats(session, lawyer.id)
    return LawyerResponse(
        id=lawyer.id,
        user_id=lawyer.user_id,
        service_type=IndividualServiceType(lawyer.service_type),
        status=lawyer.status,
        bar_number=lawyer.bar_number,
        license_jurisdiction=lawyer.license_jurisdiction,
        firm_name=lawyer.firm_name,
        specializations=lawyer.specializations,
        bio=lawyer.bio,
        years_experience=lawyer.years_experience,
        average_rating=avg_rating,
        contract_count=contract_count,
        promoted_at=lawyer.promoted_at,
        created_at=lawyer.created_at,
        updated_at=lawyer.updated_at,
    )


def touch_lawyer_updated(lawyer: Lawyer) -> None:
    lawyer.updated_at = datetime.now(timezone.utc)
