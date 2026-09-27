import pytest

from app.jobs.models import ErrorCode, IllegalTransition, JobStatus, Stage
from app.jobs.store import SQLiteJobStore


@pytest.fixture
def store(tmp_path):
    return SQLiteJobStore(tmp_path / "jobs.sqlite3")


def test_create_starts_queued_with_event(store):
    job = store.create("How does the pH scale work?", "ph_scale")
    assert job.status == JobStatus.QUEUED
    assert job.stage == Stage.QUEUED
    assert [e.kind for e in job.events] == ["created"]


def test_happy_path_lifecycle(store):
    job = store.create("q", "ph_scale")
    for stage in (Stage.PLANNING, Stage.NARRATING, Stage.RENDERING, Stage.COMPOSING, Stage.VERIFYING):
        store.start_stage(job.id, stage)
    store.record_plan(job.id, "abc123", "provider", "1.0.0")
    store.succeed(job.id, duration_s=72.5, qa={"passed": True})

    done = store.get(job.id)
    assert done.status == JobStatus.SUCCEEDED
    assert done.stage == Stage.DONE
    assert done.plan_hash == "abc123"
    assert done.duration_s == 72.5
    assert done.qa == {"passed": True}
    assert [e.kind for e in done.events] == ["created"] + ["stage"] * 5 + ["succeeded"]


def test_failure_records_code_stage_and_message(store):
    job = store.create("q", "ph_scale")
    store.start_stage(job.id, Stage.NARRATING)
    store.fail(job.id, ErrorCode.TTS_FAILED, Stage.NARRATING, "segment 3 was silent")

    failed = store.get(job.id)
    assert failed.status == JobStatus.FAILED
    assert (failed.error_code, failed.error_stage) == ("TTS_FAILED", "narrating")
    assert failed.error_message == "segment 3 was silent"


def test_terminal_jobs_cannot_transition(store):
    job = store.create("q", "ph_scale")
    store.start_stage(job.id, Stage.PLANNING)
    store.succeed(job.id, duration_s=60.0, qa={})
    with pytest.raises(IllegalTransition):
        store.start_stage(job.id, Stage.NARRATING)
    with pytest.raises(IllegalTransition):
        store.fail(job.id, ErrorCode.INTERNAL, Stage.DONE, "late failure")


def test_recover_interrupted_fails_active_jobs_only(store):
    queued = store.create("q1", "ph_scale")
    running = store.create("q2", "ph_scale")
    store.start_stage(running.id, Stage.RENDERING)
    finished = store.create("q3", "ph_scale")
    store.start_stage(finished.id, Stage.PLANNING)
    store.succeed(finished.id, duration_s=60.0, qa={})

    recovered = store.recover_interrupted()

    assert set(recovered) == {queued.id, running.id}
    assert store.get(running.id).error_code == "INTERRUPTED"
    assert store.get(running.id).error_stage == "rendering"
    assert store.get(finished.id).status == JobStatus.SUCCEEDED


def test_list_is_newest_first_and_state_survives_reopen(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    first = SQLiteJobStore(path).create("q1", "ph_scale")
    second = SQLiteJobStore(path).create("q2", "covalent_bonds")
    assert [j.id for j in SQLiteJobStore(path).list()] == [second.id, first.id]


def test_get_unknown_returns_none(store):
    assert store.get("missing") is None
