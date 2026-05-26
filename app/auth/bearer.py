import secrets

from app.secrets.loader import get_secrets_store
from app.auth.types import BearerTokenEntry 

_store_cache: list[BearerTokenEntry] | None = None



def _get_tokens() -> list[BearerTokenEntry]:
    global _store_cache
    if _store_cache is None:
        _store_cache = get_secrets_store().get_bearer_tokens()
    return _store_cache


def invalidate_token_cache() -> None:
    global _store_cache
    _store_cache = None


def validate_bearer_token(token: str) -> BearerTokenEntry | None:
    for entry in _get_tokens():
        if secrets.compare_digest(token, entry.token):
            return entry
    return None
