"""API + worker behaviour with fake pipeline runners (no Piper/ffmpeg needed)."""

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.artifacts.store import LocalArtifactStore
from app.config import Settings
from app.generation.contracts import PipelineError, PipelineResult
from app.jobs.models import ErrorCode, Stage
from app.jobs.store import SQLiteJobStore
from app.main import create_app

PH = "How does the pH scale work?"


def make_settings(tmp_path: Path, timeout_s: float = 5.0) -> Settings:
    return Settings(data_dir=tmp_path, voice_model=tmp_path / "missing.onnx", job_timeout_s=timeout_s)


def publishing_runner(settings: Settings, gate: threading.Event | None = None):
    artifacts = LocalArtifactStore(settings.artifacts_dir)

    def run(job, sink):
        sink.stage(Stage.PLANNING)
        sink.plan("hash123", "provider")
        if gate is not None:
            gate.wait(timeout=5)
        work = artifacts.workspace(job.id)
        (work / "video.mp4").write_bytes(b"fake-mp4")
        (work / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
        artifacts.publish(job.id, {"video.mp4": work / "video.mp4", "captions.srt": work / "captions.srt"})
        return PipelineResult(duration_s=61.0, qa={"passed": True})

    return run


def wait_for_terminal(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/videos/{job_id}").json()
        if body["status"] in ("succeeded", "failed"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish: {body}")


def test_submit_poll_and_download(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, publishing_runner(settings))) as client:
        created = client.post("/videos", json={"query": PH})
        assert created.status_code == 202
        job = created.json()
        assert job["status"] == "queued" and job["topic_id"] == "ph_scale"
        assert job["links"]["file"] == f"/videos/{job['id']}/file"

        done = wait_for_terminal(client, job["id"])
        assert done["status"] == "succeeded" and done["stage"] == "done"
        assert done["plan_hash"] == "hash123" and done["duration_s"] == 61.0
        assert [e["kind"] for e in done["events"]] == ["created", "stage", "succeeded"]

        video = client.get(f"/videos/{job['id']}/file")
        assert video.status_code == 200
        assert video.headers["content-type"] == "video/mp4"
        assert video.content == b"fake-mp4"
        assert client.get(f"/videos/{job['id']}/captions").status_code == 200
        assert [j["id"] for j in client.get("/videos").json()] == [job["id"]]


def test_file_is_409_while_job_is_running(tmp_path):
    settings = make_settings(tmp_path)
    gate = threading.Event()
    with TestClient(create_app(settings, publishing_runner(settings, gate))) as client:
        job_id = client.post("/videos", json={"query": PH}).json()["id"]
        response = client.get(f"/videos/{job_id}/file")
        assert response.status_code == 409
        assert response.json()["detail"]["error"] == "VIDEO_NOT_READY"
        gate.set()
        assert wait_for_terminal(client, job_id)["status"] == "succeeded"


def test_unsupported_query_is_rejected_without_creating_a_job(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, publishing_runner(settings))) as client:
        response = client.post("/videos", json={"query": "What is photosynthesis?"})
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["error"] == "UNSUPPORTED_TOPIC"
        assert len(detail["supported_queries"]) == 3
        assert detail["query"] == "What is photosynthesis?" and "photosynthesis" in detail["message"]
        assert client.get("/videos").json() == []


@pytest.mark.parametrize("query", ["", "   ", "x" * 301])
def test_malformed_queries_are_rejected(tmp_path, query):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, publishing_runner(settings))) as client:
        assert client.post("/videos", json={"query": query}).status_code == 422
        assert client.get("/videos").json() == []


def test_unknown_job_is_404(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, publishing_runner(settings))) as client:
        assert client.get("/videos/nope").status_code == 404
        assert client.get("/videos/nope/file").status_code == 404


def test_pipeline_error_becomes_failed_job_with_code_and_stage(tmp_path):
    def failing(job, sink):
        sink.stage(Stage.NARRATING)
        raise PipelineError(ErrorCode.TTS_FAILED, Stage.NARRATING, "segment 2 silent after 3 attempts")

    with TestClient(create_app(make_settings(tmp_path), failing)) as client:
        job_id = client.post("/videos", json={"query": PH}).json()["id"]
        done = wait_for_terminal(client, job_id)
        assert (done["status"], done["error_code"], done["error_stage"]) == ("failed", "TTS_FAILED", "narrating")
        assert client.get(f"/videos/{job_id}/file").status_code == 409


def test_unexpected_exception_becomes_internal_error(tmp_path):
    def crashing(job, sink):
        sink.stage(Stage.RENDERING)
        raise ValueError("boom")

    with TestClient(create_app(make_settings(tmp_path), crashing)) as client:
        job_id = client.post("/videos", json={"query": PH}).json()["id"]
        done = wait_for_terminal(client, job_id)
        assert (done["error_code"], done["error_stage"]) == ("INTERNAL", "rendering")
        assert "boom" in done["error_message"]


def test_slow_job_times_out(tmp_path):
    def slow(job, sink):
        sink.stage(Stage.RENDERING)
        time.sleep(1.0)
        sink.stage(Stage.COMPOSING)  # raises JobAbandoned: the worker already gave up
        return PipelineResult(duration_s=1.0)

    with TestClient(create_app(make_settings(tmp_path, timeout_s=0.2), slow)) as client:
        job_id = client.post("/videos", json={"query": PH}).json()["id"]
        done = wait_for_terminal(client, job_id)
        assert (done["error_code"], done["error_stage"]) == ("TIMEOUT", "rendering")
        time.sleep(1.2)  # let the abandoned thread wake up; the job must stay failed
        assert client.get(f"/videos/{job_id}").json()["status"] == "failed"


def test_startup_marks_jobs_from_previous_run_as_interrupted(tmp_path):
    settings = make_settings(tmp_path)
    orphan = SQLiteJobStore(settings.db_path).create(PH, "ph_scale")
    with TestClient(create_app(settings, publishing_runner(settings))) as client:
        body = client.get(f"/videos/{orphan.id}").json()
        assert (body["status"], body["error_code"]) == ("failed", "INTERRUPTED")


def test_topics_and_health(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, publishing_runner(settings))) as client:
        assert {t["id"] for t in client.get("/topics").json()} == {
            "ph_scale", "covalent_bonds", "ionic_vs_covalent",
        }
        health = client.get("/health").json()
        assert health["status"] == "degraded" and health["checks"]["voice_model"] is False
