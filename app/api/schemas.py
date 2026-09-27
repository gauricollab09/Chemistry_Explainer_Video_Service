"""HTTP request/response shapes. Kept separate from the internal Job model on purpose."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.jobs.models import Job


class VideoRequest(BaseModel):
    query: str = Field(min_length=3, max_length=300, examples=["How does the pH scale work?"])

    @field_validator("query")
    @classmethod
    def strip(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("query must contain at least 3 characters")
        return value


class Links(BaseModel):
    self: str
    file: str
    captions: str


class EventOut(BaseModel):
    at: str
    stage: str
    kind: str
    message: str
    data: dict[str, Any]


class JobSummary(BaseModel):
    id: str
    query: str
    topic_id: str
    status: str
    stage: str
    created_at: str
    updated_at: str
    error_code: str | None
    links: Links

    @classmethod
    def from_job(cls, job: Job) -> "JobSummary":
        return cls(**_summary_fields(job))


class JobDetail(JobSummary):
    error_stage: str | None
    error_message: str | None
    plan_hash: str | None
    plan_source: str | None
    pipeline_version: str | None
    duration_s: float | None
    qa: dict[str, Any] | None
    events: list[EventOut]

    @classmethod
    def from_job(cls, job: Job) -> "JobDetail":
        return cls(
            **_summary_fields(job),
            error_stage=job.error_stage,
            error_message=job.error_message,
            plan_hash=job.plan_hash,
            plan_source=job.plan_source,
            pipeline_version=job.pipeline_version,
            duration_s=job.duration_s,
            qa=job.qa,
            events=[EventOut(**vars(e)) for e in job.events],
        )


class TopicOut(BaseModel):
    id: str
    subject: str
    title: str
    canonical_query: str


def _summary_fields(job: Job) -> dict[str, Any]:
    base = f"/videos/{job.id}"
    return dict(
        id=job.id, query=job.query, topic_id=job.topic_id, status=job.status, stage=job.stage,
        created_at=job.created_at, updated_at=job.updated_at, error_code=job.error_code,
        links=Links(self=base, file=f"{base}/file", captions=f"{base}/captions"),
    )
