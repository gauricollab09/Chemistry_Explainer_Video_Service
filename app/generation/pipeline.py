"""The generation pipeline: plan → narrate → render → compose → verify → publish.

Each stage reports progress through the sink, and every failure leaves as a PipelineError carrying an
explicit code and stage. Output is published only after the final QA gate passes.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager

from app.artifacts.store import LocalArtifactStore
from app.config import Settings
from app.generation.compose import ComposeError, mux
from app.generation.contracts import PipelineError, PipelineResult, ProgressSink
from app.generation.qa import verify
from app.generation.render.registry import RENDERERS
from app.generation.render.video import render_video
from app.generation.script_provider import ScriptProvider, StubScriptProvider
from app.generation.timeline import FPS, assemble, to_srt
from app.generation.topics import TopicRegistry
from app.generation.tts import FaultInjectingTTS, PiperTTS, TTSProvider, narrate
from app.generation.validate import plan_with_retries
from app.jobs.models import ErrorCode, Job, Stage

COMPOSE_ATTEMPTS = 2


@contextmanager
def _stage(sink: ProgressSink, stage: Stage) -> Iterator[None]:
    sink.stage(stage)
    started = time.monotonic()
    yield
    ms = round((time.monotonic() - started) * 1000)
    sink.event("stage_done", f"{stage} finished in {ms} ms", {"duration_ms": ms})


class Pipeline:
    def __init__(self, settings: Settings, artifacts: LocalArtifactStore, registry: TopicRegistry,
                 provider: ScriptProvider | None = None, tts: TTSProvider | None = None):
        self._settings, self._artifacts, self._registry = settings, artifacts, registry
        self._provider = provider or StubScriptProvider(settings.faults)
        self._tts = tts or PiperTTS(settings.voice_model)

    def __call__(self, job: Job, sink: ProgressSink) -> PipelineResult:
        faults = self._settings.faults
        topic = self._registry.get(job.topic_id)
        work = self._artifacts.workspace(job.id)

        with _stage(sink, Stage.PLANNING):
            plan, source = plan_with_retries(self._provider, topic, job.query, RENDERERS, sink)
            sink.plan(plan.plan_hash(), source)
            (work / "plan.json").write_text(plan.model_dump_json(indent=2))

        with _stage(sink, Stage.NARRATING):
            tts = FaultInjectingTTS(self._tts, faults) if faults else self._tts
            audios = narrate(plan, tts, sink)
            track, cues, total_frames = assemble(plan, audios)
            track.write_wav(work / "narration.wav")
            (work / "captions.srt").write_text(to_srt(cues))

        with _stage(sink, Stage.RENDERING):
            try:
                stats = render_video(plan, cues, total_frames, work / "video_only.mp4")
            except Exception as e:  # deterministic code: retrying would fail the same way
                raise PipelineError(ErrorCode.RENDER_FAILED, Stage.RENDERING, f"{type(e).__name__}: {e}") from e
            sink.event("render_done", f"{stats['frames']} frames ({stats['drawn_frames']} drawn)", stats)

        with _stage(sink, Stage.COMPOSING):
            for attempt in range(1, COMPOSE_ATTEMPTS + 1):
                try:
                    if "compose_fail_once" in faults and attempt == 1:
                        raise ComposeError("injected fault: compose_fail_once")
                    mux(work / "video_only.mp4", work / "narration.wav", work / "video.mp4")
                    break
                except ComposeError as e:
                    sink.event("compose_rejected", f"attempt {attempt}: {e}", {"attempt": attempt})
            else:
                raise PipelineError(ErrorCode.COMPOSE_FAILED, Stage.COMPOSING, f"mux failed {COMPOSE_ATTEMPTS} attempts")

        with _stage(sink, Stage.VERIFYING):
            expected_s = total_frames / FPS
            qa = verify(work / "video.mp4", expected_s)
            failed = [name for name, check in qa["checks"].items() if not check["ok"]]
            sink.event("qa_report", "passed" if not failed else f"failed: {failed}", qa)
            if failed:
                raise PipelineError(ErrorCode.QA_FAILED, Stage.VERIFYING, f"quality checks failed: {failed}", qa)

        manifest = {
            "job_id": job.id, "query": job.query, "topic_id": topic.id,
            "pipeline_version": self._settings.pipeline_version,
            "plan_hash": plan.plan_hash(), "plan_source": source,
            "duration_s": qa["duration_s"],
            "segments": [
                {"scene": c.scene_index, "show": c.show, "start": round(c.start, 3), "end": round(c.end, 3), "text": c.text}
                for c in cues
            ],
            "qa": qa,
        }
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2))
        self._artifacts.publish(job.id, {
            name: work / name for name in ("video.mp4", "captions.srt", "plan.json", "manifest.json")
        })
        return PipelineResult(duration_s=qa["duration_s"], qa=qa)
