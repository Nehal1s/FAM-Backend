from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.api.deps import CORRELATION_HEADER
from app.api.routes import lawyers, profile, users
from app.auth.bearer import invalidate_token_cache
from app.config import get_settings
from app.db.engine import dispose_engine, init_engine
from app.exceptions import DbTimeoutError
from app.logging.setup import configure_logging
from app.secrets.loader import get_secrets_store

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    logger.info("app_starting", environment=settings.environment)

    tokens = get_secrets_store().get_bearer_tokens()
    if not tokens:
        logger.warning(
            "no_bearer_tokens_loaded",
            hint="Set BEARER_TOKENS_JSON in .env or bearer_tokens in AUTH_SECRET_ARN secret",
        )
    else:
        logger.info("bearer_tokens_loaded", count=len(tokens), ids=[t.id for t in tokens])
    init_engine()

    yield

    await dispose_engine()
    invalidate_token_cache()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        # Avoid 307 redirects on POST /users -> /users/ that strip Authorization headers
        redirect_slashes=False,
    )

    application.include_router(users.router)
    application.include_router(lawyers.router)
    application.include_router(profile.router)

    @application.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        response: Response = await call_next(request)
        correlation_id = getattr(request.state, "correlation_id", None)
        if correlation_id:
            response.headers[CORRELATION_HEADER] = correlation_id
        return response

    @application.get("/health")
    async def health():
        return {"status": "ok"}

    @application.exception_handler(DbTimeoutError)
    async def db_timeout_handler(request: Request, exc: DbTimeoutError):
        return JSONResponse(
            status_code=504,
            content={"detail": str(exc)},
        )

    return application


app = create_app()
