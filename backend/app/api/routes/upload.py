"""Upload your own job-posting CSV and analyse it."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.models import UploadSummary
from app.services.upload_service import (
    MAX_BYTES, MAX_ROWS, UploadError, delete_upload, load_upload, process_upload,
)

router = APIRouter(tags=["upload"])


@router.get("/upload/limits")
def limits() -> dict:
    """What the upload accepts. The UI shows this before a file is chosen."""
    return {
        "max_bytes": MAX_BYTES,
        "max_mb": MAX_BYTES // (1024 * 1024),
        "max_rows": MAX_ROWS,
        "required_columns": {
            "date": "any column named like date / posted / created / listed",
            "description": "any column named like description / text / summary",
        },
        "modes": {
            "append": "Splice onto the historical corpus so the forecast "
                      "origin moves to your latest month.",
            "standalone": "Analyse your file alone. Needs >= 12 months of "
                          "history to forecast.",
        },
        "note": "Column names are auto-detected; override them if detection "
                "picks the wrong one.",
    }


@router.post("/upload", response_model=UploadSummary)
async def upload_csv(
    file: UploadFile = File(...),
    mode: str = Form("append"),
    date_column: str | None = Form(None),
    text_column: str | None = Form(None),
) -> UploadSummary:
    """Validate, clean, extract skills and aggregate an uploaded CSV."""
    raw = await file.read()
    try:
        summary = process_upload(
            raw,
            filename=file.filename or "upload.csv",
            mode=mode,
            date_column=date_column or None,
            text_column=text_column or None,
        )
    except UploadError as exc:
        # User error, not server error -- the message is written to be shown.
        raise HTTPException(400, str(exc)) from exc

    return UploadSummary(**summary)


@router.get("/upload/{upload_id}", response_model=UploadSummary)
def get_upload(upload_id: str) -> UploadSummary:
    try:
        _, summary = load_upload(upload_id)
    except UploadError as exc:
        raise HTTPException(404, str(exc)) from exc
    return UploadSummary(**summary)


@router.delete("/upload/{upload_id}")
def remove_upload(upload_id: str) -> dict:
    delete_upload(upload_id)
    return {"deleted": upload_id}
