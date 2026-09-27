"""Job state: the lifecycle vocabulary shared by the API, the worker and the store."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Stage(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    NARRATING = "narrating"
    RENDERING = "rendering"
    COMPOSING = "composing"
    VERIFYING = "verifying"
    DONE = "done"


class ErrorCode(StrEnum):
    PLAN_INVALID = "PLAN_INVALID"
    TTS_FAILED = "TTS_FAILED"
    RENDER_FAILED = "RENDER_FAILED"
    COMPOSE_FAILED = "COMPOSE_FAILED"
    QA_FAILED = "QA_FAILED"
    TIMEOUT = "TIMEOUT"
    INTERRUPTED = "INTERRUPTED"
    INTERNAL = "INTERNAL"


# Which status a job may move to from its current status. Terminal states are final.
ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.FAILED},
    JobStatus.RUNNING: {JobStatus.RUNNING, JobStatus.SUCCEEDED, JobStatus.FAILED},
    JobStatus.SUCCEEDED: set(),
    JobStatus.FAILED: set(),
}


class IllegalTransition(Exception):
    pass


@dataclass
class JobEvent:
    at: str
    stage: str
    kind: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Job:
    id: str
    query: str
    topic_id: str
    status: JobStatus
    stage: Stage
    created_at: str
    updated_at: str
    error_code: str | None = None
    error_stage: str | None = None
    error_message: str | None = None
    plan_hash: str | None = None
    plan_source: str | None = None
    pipeline_version: str | None = None
    duration_s: float | None = None
    qa: dict[str, Any] | None = None
    events: list[JobEvent] = field(default_factory=list)
