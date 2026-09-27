"""The contract between the job worker and the generation pipeline.

The worker only knows: call the runner with a job and a progress sink, get back a PipelineResult or a
PipelineError. Everything about LLMs, TTS and ffmpeg stays behind this line.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.jobs.models import ErrorCode, Job, Stage


@dataclass
class PipelineResult:
    duration_s: float
    qa: dict[str, Any] = field(default_factory=dict)


class PipelineError(Exception):
    def __init__(self, code: ErrorCode, stage: Stage, message: str, qa: dict[str, Any] | None = None):
        super().__init__(f"{code} at {stage}: {message}")
        self.code, self.stage, self.message, self.qa = code, stage, message, qa


class ProgressSink(Protocol):
    def stage(self, stage: Stage) -> None: ...
    def event(self, kind: str, message: str, data: dict[str, Any] | None = None) -> None: ...
    def plan(self, plan_hash: str, plan_source: str) -> None: ...


Runner = Callable[[Job, ProgressSink], PipelineResult]
