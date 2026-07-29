"""Request-scoped auth identity (JWT-ready)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from backend.config import settings

ANONYMOUS_USER_ID = getattr(settings, "ANONYMOUS_USER_ID", "anonymous") or "anonymous"


@dataclass
class AuthUser:
    """
    Resolved caller identity for the current HTTP request.

    Compatible with future JWT claims: ``sub`` maps to ``user_id`` / ``external_sub``.
    """

    user_id: str = ANONYMOUS_USER_ID
    is_anonymous: bool = True
    email: Optional[str] = None
    display_name: Optional[str] = None
    external_sub: Optional[str] = None
    # Full JWT claims when authenticated via Bearer token
    claims: dict[str, Any] = field(default_factory=dict)
    auth_method: str = "anonymous"  # anonymous | header | jwt

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "is_anonymous": self.is_anonymous,
            "email": self.email,
            "display_name": self.display_name,
            "external_sub": self.external_sub,
            "auth_method": self.auth_method,
        }
