import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Set env before app imports
os.environ.setdefault(
    "BEARER_TOKENS_JSON",
    '[{"id": "test", "token": "valid-token"}]',
)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://user:pass@localhost:5432/fam_test",
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    from app.config import get_settings

    get_settings.cache_clear()
    from app.auth.bearer import invalidate_token_cache
    from app.secrets.loader import reset_secrets_store

    reset_secrets_store()
    invalidate_token_cache()

    with (
        patch("app.main.init_engine"),
        patch("app.main.dispose_engine", new_callable=AsyncMock),
    ):
        from app.main import create_app

        application = create_app()
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    get_settings.cache_clear()
    reset_secrets_store()
    invalidate_token_cache()


AUTH_HEADER = {"Authorization": "Bearer valid-token"}
