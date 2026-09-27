"""End-to-end with the real pipeline (Piper + Pillow + ffmpeg). Run with: uv run pytest -m slow -v"""

import time

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, Settings
from app.main import create_app

pytestmark = pytest.mark.slow

VOICE = ROOT / "voices" / "en_US-lessac-medium.onnx"
QUERIES = {
    "ph_scale": "How does the pH scale work?",
    "covalent_bonds": "Why do atoms form covalent bonds?",
    "ionic_vs_covalent": "What is the difference between ionic and covalent bonding?",
}


def settings(tmp_path, faults=()):
    if not VOICE.is_file():
        pytest.skip("voice model missing: run scripts/setup.sh")
    return Settings(data_dir=tmp_path, voice_model=VOICE, faults=frozenset(faults))


def run(client: TestClient, query: str, timeout: float = 600) -> dict:
    job_id = client.post("/videos", json={"query": query}).json()["id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/videos/{job_id}").json()
        if body["status"] in ("succeeded", "failed"):
            return body
        time.sleep(1)
    raise AssertionError(f"{query!r} did not finish in {timeout}s")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(create_app(settings(tmp_path_factory.mktemp("e2e")))) as c:
        yield c


@pytest.mark.parametrize("topic_id", QUERIES)
def test_required_query_produces_a_verified_video(client, topic_id):
    job = run(client, QUERIES[topic_id])
    assert job["status"] == "succeeded", job
    assert job["topic_id"] == topic_id
    assert job["qa"]["passed"] and all(c["ok"] for c in job["qa"]["checks"].values())
    assert 45 <= job["duration_s"] <= 120
    video = client.get(f"/videos/{job['id']}/file")
    assert video.status_code == 200 and video.content[4:8] == b"ftyp"


def test_same_query_twice_gives_the_same_plan_and_consistent_video(client):
    first, second = run(client, QUERIES["covalent_bonds"]), run(client, QUERIES["covalent_bonds"])
    assert first["status"] == second["status"] == "succeeded"
    assert first["plan_hash"] == second["plan_hash"]
    # Piper samples noise, so speech length varies slightly run to run; the timeline absorbs it.
    assert abs(first["duration_s"] - second["duration_s"]) < 2.0


def test_injected_faults_are_recovered_or_reported(tmp_path):
    with TestClient(create_app(settings(tmp_path, {"plan_invalid_once", "tts_silent_always"}))) as c:
        job = run(c, QUERIES["ph_scale"])
    kinds = [e["kind"] for e in job["events"]]
    assert "plan_rejected" in kinds and "plan_accepted" in kinds  # bad plan retried and recovered
    assert (job["status"], job["error_code"], job["error_stage"]) == ("failed", "TTS_FAILED", "narrating")
    assert kinds.count("tts_rejected") == 3
