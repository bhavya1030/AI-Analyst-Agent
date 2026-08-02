"""Upload route — POST /upload."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.utils.json_safe import sanitize_for_json

router = APIRouter(tags=["upload"])


@router.post("/upload")
def upload_dataset(file: UploadFile = File(...)):
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    filename = Path(file.filename or "").name
    if not filename:
        return JSONResponse(
            status_code=400,
            content={"error": "A valid filename is required."},
        )

    upload_path = settings.DATA_DIR / filename

    try:
        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return sanitize_for_json(
            {
                "message": "Dataset uploaded successfully",
                "file_path": str(upload_path),
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": f"Upload failed: {exc}"},
        )
