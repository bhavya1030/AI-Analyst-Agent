"""Analyze route — GET /analyze."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.auth.context import AuthUser
from backend.auth.deps import get_current_user
from backend.orchestrator.request_orchestrator import get_orchestrator

router = APIRouter(tags=["analyze"])


@router.get("/analyze")
def analyze(
    session_id: str = "default",
    user: AuthUser = Depends(get_current_user),
):
    return get_orchestrator().run_analyze(
        session_id=session_id,
        user_id=user.user_id,
    )
