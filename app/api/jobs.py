"""Job status & result endpoints."""

from fastapi.responses import PlainTextResponse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import Job, User
from app.api.deps import get_current_user

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


def _result_to_markdown(job: Job) -> str:
    source = job.source_meta or {}
    transcript = job.transcript or {}
    summary = job.summary or {}

    lines = []
    lines.append("# AI Summary Result")
    lines.append("")
    lines.append(f"- Job ID: `{job.id}`")
    lines.append(f"- Source Type: `{job.source_type}`")
    if source.get("title"):
        lines.append(f"- Title: {source.get('title')}")
    if source.get("filename"):
        lines.append(f"- File: {source.get('filename')}")
    if source.get("url"):
        lines.append(f"- URL: {source.get('url')}")
    lines.append("")

    lines.append("## TL;DR")
    lines.append(summary.get("tl_dr") or "—")
    lines.append("")

    lines.append("## Key Points")
    for p in (summary.get("key_points") or []):
        lines.append(f"- {p}")
    if not (summary.get("key_points") or []):
        lines.append("- —")
    lines.append("")

    lines.append("## Outline")
    outline = summary.get("outline") or []
    if outline:
        for sec in outline:
            title = sec.get("title") if isinstance(sec, dict) else str(sec)
            lines.append(f"### {title or 'Section'}")
            points = sec.get("points", []) if isinstance(sec, dict) else []
            for point in points:
                lines.append(f"- {point}")
            lines.append("")
    else:
        lines.append("- —")
        lines.append("")

    lines.append("## Action Items")
    for a in (summary.get("action_items") or []):
        lines.append(f"- [ ] {a}")
    if not (summary.get("action_items") or []):
        lines.append("- —")
    lines.append("")

    lines.append("## Timestamps")
    for ts in (summary.get("timestamps") or []):
        t = ts.get("t", "--:--:--")
        label = ts.get("label", "")
        lines.append(f"- **{t}** {label}")
    if not (summary.get("timestamps") or []):
        lines.append("- —")
    lines.append("")

    lines.append("## Transcript")
    lines.append("```text")
    lines.append(transcript.get("text") or "")
    lines.append("```")

    return "\n".join(lines).strip() + "\n"


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


@router.get("/{job_id}/result.md", response_class=PlainTextResponse)
def get_job_result_markdown(
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

    filename = f"ai-summary-{job.id}.md"
    return PlainTextResponse(
        content=_result_to_markdown(job),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
