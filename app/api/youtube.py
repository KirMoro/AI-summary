"""POST /v1/youtube — submit YouTube URL for processing."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from redis import Redis
from rq import Queue

from app.config import settings
from app.db.database import get_db
from app.db.models import Job, User
from app.api.deps import get_current_user

router = APIRouter(prefix="/v1", tags=["youtube"])


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

    # Enqueue background task
    conn = Redis.from_url(settings.redis_url)
    q = Queue(settings.rq_queue_name, connection=conn)
    q.enqueue(
        "app.workers.tasks.process_youtube",
        str(job.id),
        job_timeout=settings.job_timeout,
    )

    return JobCreated(job_id=str(job.id), status=job.status)
