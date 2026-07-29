"""Authentication preparation (Phase 8).

Provides User model, request identity resolution, and session ownership helpers.
Login UI is intentionally out of scope — clients may send X-User-Id or a future JWT.
"""

from backend.auth.context import AuthUser, ANONYMOUS_USER_ID
from backend.auth.deps import get_current_user, get_current_user_id
from backend.auth.models import User
from backend.auth.service import UserService, ensure_auth_schema, get_user_service

__all__ = [
    "AuthUser",
    "ANONYMOUS_USER_ID",
    "User",
    "UserService",
    "get_user_service",
    "ensure_auth_schema",
    "get_current_user",
    "get_current_user_id",
]
