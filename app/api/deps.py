from uuid import uuid4

from fastapi import Depends, Header, Request

from app.auth.base import AuthContext, require_auth
from app.auth.rate_limit import check_rate_limit
from app.logging.setup import bind_correlation_id

CORRELATION_HEADER = "X-Correlation-ID"


async def get_correlation_id(
    request: Request,
    x_correlation_id: str | None = Header(default=None, alias=CORRELATION_HEADER),
) -> str:
    correlation_id = x_correlation_id or str(uuid4())
    bind_correlation_id(correlation_id)
    request.state.correlation_id = correlation_id
    return correlation_id


async def require_auth_and_rate_limit(
    request: Request,
    auth: AuthContext = Depends(require_auth),
) -> AuthContext:
    check_rate_limit(auth, request)
    return auth
