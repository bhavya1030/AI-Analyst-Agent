"""FastAPI dependencies for request identity (Phase 8).

Resolution order:
  1. Authorization: Bearer <jwt>  (when JWT_SECRET configured)
  2. X-User-Id header           (dev / trusted gateway)
  3. anonymous

No login page — clients supply identity headers/tokens.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status

from backend.auth.context import ANONYMOUS_USER_ID, AuthUser
from backend.auth.jwt_util import decode_bearer_token
from backend.auth.service import get_user_service, normalize_user_id
from backend.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)


def _header_name() -> str:
    return (getattr(settings, "AUTH_USER_HEADER", None) or "X-User-Id").strip()


def resolve_auth_user(
    *,
    authorization: str | None = None,
    x_user_id: str | None = None,
) -> AuthUser:
    """Pure resolver (usable outside FastAPI)."""
    # 1) JWT Bearer
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        claims = decode_bearer_token(token)
        if claims:
            sub = str(claims.get("sub") or "").strip()
            user_id = normalize_user_id(sub)
            auth = AuthUser(
                user_id=user_id,
                is_anonymous=user_id == ANONYMOUS_USER_ID,
                email=claims.get("email"),
                display_name=claims.get("name") or claims.get("display_name"),
                external_sub=sub,
                claims=dict(claims),
                auth_method="jwt",
            )
            try:
                get_user_service().ensure_from_auth(auth)
            except Exception as exc:
                logger.warning("User ensure from JWT failed", extra={"error": str(exc)})
            return auth

    # 2) Explicit user header (trusted network / gateway)
    header_val = (x_user_id or "").strip()
    if header_val:
        user_id = normalize_user_id(header_val)
        auth = AuthUser(
            user_id=user_id,
            is_anonymous=user_id == ANONYMOUS_USER_ID,
            display_name=user_id,
            external_sub=None,
            claims={},
            auth_method="header",
        )
        try:
            get_user_service().ensure_from_auth(auth)
        except Exception as exc:
            logger.warning("User ensure from header failed", extra={"error": str(exc)})
        return auth

    # 3) Anonymous
    auth = AuthUser(
        user_id=ANONYMOUS_USER_ID,
        is_anonymous=True,
        display_name="Anonymous",
        auth_method="anonymous",
    )
    try:
        get_user_service().ensure_from_auth(auth)
    except Exception:
        pass
    return auth


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> AuthUser:
    """
    FastAPI dependency: resolve AuthUser for the request.

    Also accepts dynamic header name from settings.AUTH_USER_HEADER.
    """
    # Support custom header name from config
    custom_header = _header_name()
    if custom_header.lower() != "x-user-id":
        alt = request.headers.get(custom_header) or request.headers.get(
            custom_header.lower()
        )
        if alt:
            x_user_id = alt

    auth = resolve_auth_user(authorization=authorization, x_user_id=x_user_id)

    if bool(getattr(settings, "REQUIRE_AUTH", False)) and auth.is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Authentication required",
                "code": "AUTH_REQUIRED",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Stash on request.state for non-DI access
    try:
        request.state.auth_user = auth
        request.state.user_id = auth.user_id
    except Exception:
        pass

    return auth


async def get_current_user_id(
    user: AuthUser = Depends(get_current_user),
) -> str:
    return user.user_id


def get_request_user_id(request: Request) -> str:
    """Sync helper for routes that do not use Depends."""
    auth = getattr(request.state, "auth_user", None)
    if isinstance(auth, AuthUser):
        return auth.user_id
    # Resolve from headers without requiring async
    authorization = request.headers.get("Authorization")
    x_user_id = request.headers.get("X-User-Id") or request.headers.get(
        _header_name()
    )
    return resolve_auth_user(
        authorization=authorization, x_user_id=x_user_id
    ).user_id
