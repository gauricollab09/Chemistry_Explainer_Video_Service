"""Async job execution: an in-process queue with one worker.

The runner (the generation pipeline) is blocking, so it runs in a thread. This class is the swap point
for Celery / Cloud Tasks: the contract (job in, PipelineResult or PipelineError out) stays the same.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.generation.contracts import PipelineError, Runner
from app.jobs.models import ErrorCode, Stage
from app.jobs.store import SQLiteJobStore

log = logging.getLogger("chemvid.worker")


class JobAbandoned(Exception):
    """Raised inside the pipeline thread once the worker has given up on the job (e.g. timeout)."""


class StoreSink:
    """ProgressSink that writes a job's progress into the JobStore and the logs."""

    def __init__(self, store: SQLiteJobStore, job_id: str, pipeline_version: str):
        self._store, self._job_id, self._version = store, job_id, pipeline_version
        self.current = Stage.QUEUED
        self.abandoned = False

    def stage(self, stage: Stage) -> None:
        self._check()
        self._store.start_stage(self._job_id, stage)
        self.current = stage
        log.info("job=%s stage=%s", self._job_id, stage)

    def event(self, kind: str, message: str, data: dict[str, Any] | None = None) -> None:
        self._check()
        self._store.add_event(self._job_id, self.current, kind, message, data)
        log.info("job=%s stage=%s %s: %s %s", self._job_id, self.current, kind, message, data or "")

    def plan(self, plan_hash: str, plan_source: str) -> None:
        self._check()
        self._store.record_plan(self._job_id, plan_hash, plan_source, self._version)

    def _check(self) -> None:
        if self.abandoned:
            log.warning("job=%s abandoned after timeout; pipeline thread stopped at stage=%s, nothing published",
                        self._job_id, self.current)
            raise JobAbandoned(self._job_id)


class Worker:
    def __init__(self, store: SQLiteJobStore, runner: Runner, timeout_s: float, pipeline_version: str):
        self._store, self._runner = store, runner
        self._timeout_s, self._version = timeout_s, pipeline_version
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="video-worker")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def submit(self, job_id: str) -> None:
        self._queue.put_nowait(job_id)

    async def _loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._process(job_id)
            except Exception:  # never let one job kill the worker
                log.exception("job=%s worker error", job_id)
            finally:
                self._queue.task_done()

    async def _process(self, job_id: str) -> None:
        job = self._store.get(job_id)
        sink = StoreSink(self._store, job_id, self._version)
        started = asyncio.get_running_loop().time()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._runner, job, sink), timeout=self._timeout_s
            )
        except PipelineError as e:
            self._store.fail(job_id, e.code, e.stage, e.message, e.qa)
        except TimeoutError:
            sink.abandoned = True  # the thread stops at its next progress report
            self._store.fail(
                job_id, ErrorCode.TIMEOUT, sink.current, f"Job exceeded {self._timeout_s:.0f}s time limit"
            )
        except Exception as e:
            log.exception("job=%s unexpected error", job_id)
            self._store.fail(job_id, ErrorCode.INTERNAL, sink.current, f"{type(e).__name__}: {e}")
        else:
            self._store.succeed(job_id, result.duration_s, result.qa)
        elapsed = asyncio.get_running_loop().time() - started
        log.info("job=%s finished status=%s in %.1fs", job_id, self._store.get(job_id).status, elapsed)
