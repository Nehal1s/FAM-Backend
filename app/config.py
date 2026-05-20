from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "fam-backend"
    environment: str = "development"
    log_level: str = "INFO"

    # Database — use DATABASE_URL locally; Secrets Manager in prod
    database_url: str | None = None
    database_secret_arn: str | None = None
    db_pool_size: int = 20
    db_max_overflow: int = 0
    db_query_timeout_ms: int = 150

    # Auth — combined secret or local override
    auth_secret_arn: str | None = None
    secrets_refresh_seconds: int = 300

    # Local dev: JSON list [{"id":"dev","token":"..."}]
    bearer_tokens_json: str | None = None

    # Rate limiting (~1000 req/min peak ≈ 17 rps; allow burst per token)
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # User session (dashboard /me) — dev-only fallback when token has no user_id
    allow_dev_user_id_header: bool = True

    # Future: JWT access tokens from login (Google, email/password)
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"

    # CloudWatch
    cloudwatch_enabled: bool = False
    cloudwatch_namespace: str = "FAM/Backend"
    aws_region: str = "us-east-1"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
