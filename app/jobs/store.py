"""Persistence boundary: SQLite-backed job store.

One short-lived connection per operation keeps it safe to call from the worker thread and the
event loop alike. Swapping to Postgres means reimplementing this class, nothing else.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.jobs.models import (
    ALLOWED_TRANSITIONS,
    ErrorCode,
    IllegalTransition,
    Job,
    JobEvent,
    JobStatus,
    Stage,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_code TEXT,
    error_stage TEXT,
    error_message TEXT,
    plan_hash TEXT,
    plan_source TEXT,
    pipeline_version TEXT,
    duration_s REAL,
    qa_json TEXT
);
CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    at TEXT NOT NULL,
    stage TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _plain(value: Any) -> Any:
    return value.value if isinstance(value, (JobStatus, Stage, ErrorCode)) else value


class SQLiteJobStore:
    def __init__(self, db_path: Path):
        self._path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._tx() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commits on success, rolls back on exception
                yield conn
        finally:
            conn.close()

    # --- reads -------------------------------------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            events = conn.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY id", (job_id,)
            ).fetchall()
        return self._to_job(row, [self._to_event(e) for e in events])

    def list(self) -> list[Job]:
        with self._tx() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC").fetchall()
        return [self._to_job(r, []) for r in rows]

    # --- writes ------------------------------------------------------------------------------

    def create(self, query: str, topic_id: str) -> Job:
        job_id = uuid.uuid4().hex[:12]
        now = _now()
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO jobs (id, query, topic_id, status, stage, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (job_id, query, topic_id, JobStatus.QUEUED.value, Stage.QUEUED.value, now, now),
            )
            self._event(conn, job_id, Stage.QUEUED, "created", f"Job created for topic '{topic_id}'")
        return self.get(job_id)

    def start_stage(self, job_id: str, stage: Stage) -> None:
        with self._tx() as conn:
            self._transition(conn, job_id, JobStatus.RUNNING, stage=stage)
            self._event(conn, job_id, stage, "stage", f"Entered stage '{stage}'")

    def record_plan(self, job_id: str, plan_hash: str, plan_source: str, pipeline_version: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE jobs SET plan_hash = ?, plan_source = ?, pipeline_version = ?, updated_at = ?"
                " WHERE id = ?",
                (plan_hash, plan_source, pipeline_version, _now(), job_id),
            )

    def succeed(self, job_id: str, duration_s: float, qa: dict[str, Any]) -> None:
        with self._tx() as conn:
            self._transition(
                conn, job_id, JobStatus.SUCCEEDED,
                stage=Stage.DONE, duration_s=duration_s, qa_json=json.dumps(qa),
            )
            self._event(conn, job_id, Stage.DONE, "succeeded", f"Video ready ({duration_s:.1f}s)")

    def fail(
        self, job_id: str, code: ErrorCode, stage: Stage, message: str, qa: dict[str, Any] | None = None
    ) -> None:
        with self._tx() as conn:
            self._transition(
                conn, job_id, JobStatus.FAILED,
                error_code=code, error_stage=stage, error_message=message,
                qa_json=json.dumps(qa) if qa is not None else None,
            )
            self._event(conn, job_id, stage, "failed", f"{code}: {message}")

    def add_event(
        self, job_id: str, stage: Stage, kind: str, message: str, data: dict[str, Any] | None = None
    ) -> None:
        with self._tx() as conn:
            self._event(conn, job_id, stage, kind, message, data)

    def recover_interrupted(self) -> list[str]:
        """Called on startup: nothing is running yet, so any active job was cut off by a restart."""
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT id, stage FROM jobs WHERE status IN (?, ?)",
                (JobStatus.QUEUED.value, JobStatus.RUNNING.value),
            ).fetchall()
            for row in rows:
                message = "Server stopped before the job finished; please resubmit the query."
                self._transition(
                    conn, row["id"], JobStatus.FAILED,
                    error_code=ErrorCode.INTERRUPTED, error_stage=row["stage"], error_message=message,
                )
                self._event(conn, row["id"], Stage(row["stage"]), "failed", f"INTERRUPTED: {message}")
        return [row["id"] for row in rows]

    # --- internals ---------------------------------------------------------------------------

    def _transition(self, conn: sqlite3.Connection, job_id: str, new_status: JobStatus, **fields: Any) -> None:
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        current = JobStatus(row["status"])
        if new_status not in ALLOWED_TRANSITIONS[current]:
            raise IllegalTransition(f"job {job_id}: {current} -> {new_status}")
        fields |= {"status": new_status, "updated_at": _now()}
        assignments = ", ".join(f"{column} = ?" for column in fields)
        values = tuple(_plain(v) for v in fields.values())
        conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*values, job_id))

    def _event(
        self, conn: sqlite3.Connection, job_id: str, stage: Stage, kind: str, message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            "INSERT INTO job_events (job_id, at, stage, kind, message, data_json) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, _now(), _plain(stage), kind, message, json.dumps(data or {})),
        )

    @staticmethod
    def _to_event(row: sqlite3.Row) -> JobEvent:
        return JobEvent(
            at=row["at"], stage=row["stage"], kind=row["kind"], message=row["message"],
            data=json.loads(row["data_json"]),
        )

    @staticmethod
    def _to_job(row: sqlite3.Row, events: list[JobEvent]) -> Job:
        return Job(
            id=row["id"], query=row["query"], topic_id=row["topic_id"],
            status=JobStatus(row["status"]), stage=Stage(row["stage"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
            error_code=row["error_code"], error_stage=row["error_stage"], error_message=row["error_message"],
            plan_hash=row["plan_hash"], plan_source=row["plan_source"],
            pipeline_version=row["pipeline_version"], duration_s=row["duration_s"],
            qa=json.loads(row["qa_json"]) if row["qa_json"] else None,
            events=events,
        )
