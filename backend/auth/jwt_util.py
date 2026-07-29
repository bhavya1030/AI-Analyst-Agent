"""Optional JWT decode helpers for future authentication (Phase 8).

Uses PyJWT when installed and JWT_SECRET is configured. Never raises to
callers for missing optional deps — returns None so header/anonymous
fallback can run.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)


def decode_bearer_token(token: str) -> Optional[dict[str, Any]]:
    """
    Validate HS256 JWT and return claims, or None if invalid / unconfigured.

    Expected claims (future):
      sub   — stable subject → user_id / external_sub
      email — optional
      name  — optional display name
    """
    secret = (getattr(settings, "JWT_SECRET", None) or "").strip()
    if not secret or not token:
        return None

    try:
        import jwt  # PyJWT
    except ImportError:
        logger.debug("PyJWT not installed; Bearer token ignored")
        return None

    algorithm = getattr(settings, "JWT_ALGORITHM", "HS256") or "HS256"
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options={"require": ["sub"]},
        )
        if not isinstance(claims, dict) or not claims.get("sub"):
            return None
        return claims
    except Exception as exc:
        logger.info("JWT validation failed", extra={"error": str(exc)})
        return None
