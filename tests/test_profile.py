from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.schemas.profile import ServiceProvidingItem, ServiceUsingItem, UserProfileDashboard
from app.schemas.service import IndividualServiceType, ServiceKind
from app.schemas.user import UserResponse
from tests.conftest import AUTH_HEADER

USER_ID = uuid4()
NOW = datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_profile_requires_user_session(client):
    response = await client.get("/me/profile", headers=AUTH_HEADER)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_profile_with_dev_user_header(client):
    profile = UserProfileDashboard(
        user=UserResponse(
            id=USER_ID,
            email="me@example.com",
            auth_method="pending",
            created_at=NOW,
            lawyer=None,
        ),
        services_providing=[],
        services_using=[],
    )
    with patch("app.api.routes.profile.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = profile
        response = await client.get(
            "/me/profile",
            headers={**AUTH_HEADER, "X-User-Id": str(USER_ID)},
        )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_profile_service_token_forbidden_without_user_id(client):
    response = await client.get("/me/profile", headers=AUTH_HEADER)
    assert response.status_code == 403
