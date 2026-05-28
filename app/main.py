from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import CORRELATION_HEADER
from app.api.routes import lawyers, profile, users
from app.api.routes.auth import router as auth_router
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
        redirect_slashes=False,
    )

    origins = [
        "http://localhost:8080",
        "http://localhost:8000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8000",
    ]

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,       # List of allowed origins
        allow_credentials=True,     # Allow cookies and authentication headers
        allow_methods=["*"],         # Allow all HTTP methods (GET, POST, etc.)
        allow_headers=["*"],         # Allow all headers
    )

    # ── Middleware ─────────────────────────────────────────────────────────────
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.jwt_secret,
        https_only=settings.cookie_secure,
    )

    # ── Routers ────────────────────────────────────────────────────────────────
    application.include_router(auth_router)
    application.include_router(users.router)
    application.include_router(lawyers.router)
    application.include_router(profile.router)

    # ── Middleware: correlation ID ─────────────────────────────────────────────
    @application.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        response: Response = await call_next(request)
        correlation_id = getattr(request.state, "correlation_id", None)
        if correlation_id:
            response.headers[CORRELATION_HEADER] = correlation_id
        return response

    # ── Routes ─────────────────────────────────────────────────────────────────
    @application.get("/health")
    async def health():
        return {"status": "ok"}

    # ── Exception handlers ─────────────────────────────────────────────────────
    @application.exception_handler(DbTimeoutError)
    async def db_timeout_handler(request: Request, exc: DbTimeoutError):
        return JSONResponse(status_code=504, content={"detail": str(exc)})

    return application


app = create_app()