"""User-facing auth method (how the account signs in). Distinct from API AuthContext.auth_method."""

from enum import StrEnum


class UserAuthMethod(StrEnum):
    """Stored on User; extend when adding Google / password flows."""

    PENDING = "pending"
    EMAIL_PASSWORD = "email_password"
    GOOGLE = "google"
    APPLE = "apple"
    STATIC_TOKEN = "static_token"  # created via trusted service / bearer until user links IdP
