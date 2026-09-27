"""HTTP layer only: validate input, talk to the store/worker/artifacts, shape responses."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.schemas import JobDetail, JobSummary, TopicOut, VideoRequest
from app.jobs.models import Job, JobStatus

router = APIRouter()


def _services(request: Request):
    return request.app.state.services


def _job_or_404(request: Request, job_id: str) -> Job:
    job = _services(request).store.get(job_id)
    if job is None:
        raise HTTPException(404, detail={"error": "NOT_FOUND", "message": f"No job with id '{job_id}'"})
    return job


@router.post("/videos", status_code=202, response_model=JobSummary)
def request_video(body: VideoRequest, request: Request) -> JobSummary:
    services = _services(request)
    topic = services.registry.resolve(body.query)
    if topic is None:
        raise HTTPException(
            422,
            detail={
                "error": "UNSUPPORTED_TOPIC",
                "message": "This query does not match a supported topic.",
                "supported_queries": [t.canonical_query for t in services.registry.all()],
            },
        )
    job = services.store.create(body.query, topic.id)
    services.worker.submit(job.id)
    return JobSummary.from_job(job)


@router.get("/videos", response_model=list[JobSummary])
def list_videos(request: Request) -> list[JobSummary]:
    return [JobSummary.from_job(j) for j in _services(request).store.list()]


@router.get("/videos/{job_id}", response_model=JobDetail)
def get_video(job_id: str, request: Request) -> JobDetail:
    return JobDetail.from_job(_job_or_404(request, job_id))


@router.get("/videos/{job_id}/file", response_class=FileResponse)
def get_video_file(job_id: str, request: Request) -> FileResponse:
    return _artifact(request, job_id, "video.mp4", "video/mp4")


@router.get("/videos/{job_id}/captions", response_class=FileResponse)
def get_video_captions(job_id: str, request: Request) -> FileResponse:
    return _artifact(request, job_id, "captions.srt", "application/x-subrip")


@router.get("/topics", response_model=list[TopicOut])
def list_topics(request: Request) -> list[TopicOut]:
    return [
        TopicOut(id=t.id, subject=t.subject, title=t.title, canonical_query=t.canonical_query)
        for t in _services(request).registry.all()
    ]


@router.get("/health")
def health(request: Request) -> dict:
    settings = _services(request).settings
    checks = {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "voice_model": settings.voice_model.is_file(),
    }
    return {"status": "ok" if all(checks.values()) else "degraded", "checks": checks}


def _artifact(request: Request, job_id: str, name: str, media_type: str) -> FileResponse:
    job = _job_or_404(request, job_id)
    if job.status != JobStatus.SUCCEEDED:
        raise HTTPException(
            409,
            detail={
                "error": "VIDEO_NOT_READY",
                "message": f"Job is '{job.status}' (stage '{job.stage}')",
                "status": job.status,
                "stage": job.stage,
                "error_code": job.error_code,
            },
        )
    path = _services(request).artifacts.get(job_id, name)
    if path is None:
        raise HTTPException(404, detail={"error": "ARTIFACT_MISSING", "message": f"{name} not found"})
    return FileResponse(path, media_type=media_type, filename=f"{job.topic_id}-{job_id}-{name}")
