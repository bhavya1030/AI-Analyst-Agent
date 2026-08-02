"""Ask routes — GET /ask and GET /v1/ask."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.auth.context import AuthUser
from backend.auth.deps import get_current_user
from backend.orchestrator.request_orchestrator import get_orchestrator

router = APIRouter(tags=["ask"])


@router.get("/v1/ask")
@router.get("/ask")
def ask(
    question: str,
    session_id: str = "default",
    file_path: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    return get_orchestrator().run_ask(
        question=question,
        session_id=session_id,
        file_path=file_path,
        user_id=user.user_id,
    )
