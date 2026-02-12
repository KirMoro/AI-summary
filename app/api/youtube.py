"""POST /v1/youtube — submit YouTube URL for processing."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.rate_limit import rate_limit
from app.config import settings
from app.db.database import get_db
from app.db.models import Job, User
from app.api.deps import get_current_user
from app.queue import enqueue_task

router = APIRouter(prefix="/v1", tags=["youtube"])
submit_limiter = rate_limit(settings.job_submit_rate_limit_per_minute, 60, "submit")


class YouTubeRequest(BaseModel):
    url: str = Field(..., description="YouTube video URL")
    summary_style: str = Field("medium", pattern="^(short|medium|detailed)$")
    language: str = Field("auto", pattern="^(ru|en|auto)$")


class JobCreated(BaseModel):
    job_id: str
    status: str


@router.post("/youtube", response_model=JobCreated)
def submit_youtube(
    body: YouTubeRequest,
    _: None = Depends(submit_limiter),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if "youtube.com" not in body.url and "youtu.be" not in body.url:
        raise HTTPException(400, "Invalid YouTube URL")

    job = Job(
        user_id=user.id,
        source_type="youtube",
        source_meta={"url": body.url},
        summary_style=body.summary_style,
        language=body.language,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    enqueue_task("app.workers.tasks.process_youtube", str(job.id))

    return JobCreated(job_id=str(job.id), status=job.status)
