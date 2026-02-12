"""POST /v1/upload — upload audio/video file for processing."""

import os
import uuid
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.api.rate_limit import rate_limit
from app.config import settings
from app.db.database import get_db
from app.db.models import Job, User
from app.api.deps import get_current_user
from app.queue import enqueue_task

router = APIRouter(prefix="/v1", tags=["upload"])
submit_limiter = rate_limit(settings.job_submit_rate_limit_per_minute, 60, "submit")

ALLOWED_EXTENSIONS = {
    ".mp3", ".mp4", ".m4a", ".wav", ".ogg", ".webm", ".flac",
    ".mpeg", ".mpga", ".avi", ".mkv", ".mov", ".wma", ".aac",
}


@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    summary_style: str = Form("medium"),
    language: str = Form("auto"),
    _: None = Depends(submit_limiter),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    if summary_style not in ("short", "medium", "detailed"):
        raise HTTPException(400, "summary_style must be short|medium|detailed")
    if language not in ("ru", "en", "auto"):
        raise HTTPException(400, "language must be ru|en|auto")

    tmp_dir = tempfile.gettempdir()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    tmp_path = os.path.join(tmp_dir, safe_name)

    size = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    with open(tmp_path, "wb") as f:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                f.close()
                os.unlink(tmp_path)
                raise HTTPException(413, f"File too large. Max {settings.max_upload_mb} MB.")
            f.write(chunk)

    job = Job(
        user_id=user.id,
        source_type="upload",
        source_meta={
            "filename": file.filename,
            "size_bytes": size,
            "tmp_path": tmp_path,
        },
        summary_style=summary_style,
        language=language,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    enqueue_task("app.workers.tasks.process_upload", str(job.id))

    return {"job_id": str(job.id), "status": job.status}
