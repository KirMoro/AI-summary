"""Job status & result endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import Job, User
from app.api.deps import get_current_user

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("/config")
def get_config():
    """Public configuration (no auth needed)."""
    return {"max_upload_mb": settings.max_upload_mb}


@router.get("/{job_id}")
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    return {
        "job_id": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "source_type": job.source_type,
        "source_meta": job.source_meta,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@router.get("/{job_id}/result")
def get_job_result(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    if job.status == "error":
        raise HTTPException(422, detail=job.error or {"message": "Processing failed"})
    if job.status != "done":
        raise HTTPException(409, "Job not done yet")

    return {
        "source": job.source_meta,
        "transcript": job.transcript,
        "summary": job.summary,
    }
