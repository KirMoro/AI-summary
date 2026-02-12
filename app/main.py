"""FastAPI application entry point."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, jobs, upload, youtube

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
log = structlog.get_logger()

app = FastAPI(
    title="AI Summary",
    description="YouTube / File → Transcript + Summary",
    version="1.0.0",
)

# CORS — allow all for personal use
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ───────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(youtube.router)
app.include_router(upload.router)
app.include_router(jobs.router)

# ── Static files & SPA fallback ─────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def index():
    return FileResponse("app/static/index.html")


@app.get("/health")
def health():
    return {"status": "ok"}
