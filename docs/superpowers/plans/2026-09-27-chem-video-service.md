# Chemistry Video Service Implementation Plan

> Execution: native (implemented in-session), one review at the end. Condensed plan (task list +
> interfaces + verification) because of the 2-hour time box; the spec carries the design.

**Goal:** FastAPI service that turns one of three chemistry queries into a narrated, animated,
QA-verified MP4 via an async job.

**Architecture:** API → SQLite `JobStore` → asyncio worker → `pipeline.run` (plan → narrate → render →
compose → verify) → `ArtifactStore` atomic publish. Providers (`ScriptProvider`, `TTSProvider`) are the
AI plug-in points.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLite (stdlib), Pydantic v2, Pillow, NumPy, Piper TTS, ffmpeg.

**Spec:** `docs/SPEC.md`

## Global Constraints
- Python 3.12; deps only via `uv add`; Intel-mac `required-environments` pin stays.
- Video: 1280×720, 30 fps, H.264 + AAC, 45–120 s; voice `en_US-lessac-medium`.
- Narration: 3–40 words per segment; ~3.1 words/s.
- Nothing is published before the QA gate passes.
- Every checkpoint appends to `PROGRESS.md` (changed / run / results / incomplete) and commits.

## Review Focus
1. Query with odd casing/punctuation/whitespace ("  HOW does the PH scale work??") → resolves to the same topic.
2. Empty or very long query → 422, no job created.
3. `GET /videos/{id}/file` while running or after failure → 409 with the job status, never a partial file.
4. Server restart mid-job → job becomes `failed/INTERRUPTED`, not stuck in `running`.
5. Same query submitted twice → identical `plan_hash`; durations within 0.1 s.

---

### Task 1 (CP3): Job layer
Files: `app/config.py`, `app/jobs/models.py`, `app/jobs/store.py`, `tests/test_job_store.py`
- `JobStatus`, `Stage`, `ErrorCode` (StrEnum), `Job`, `JobEvent`, `IllegalTransition`.
- `SQLiteJobStore(db_path)`: `create(query, topic_id) -> Job`, `get(id) -> Job|None`, `list() -> list[Job]`,
  `start_stage(id, stage)`, `record_plan(id, plan_hash, plan_source, pipeline_version)`,
  `succeed(id, duration_s, qa)`, `fail(id, code, stage, message, qa=None)`,
  `add_event(id, stage, kind, message, data=None)`, `recover_interrupted() -> list[str]`.
- Transitions: queued→{running,failed}; running→{running,succeeded,failed}; terminal→∅.
- Verify: `uv run pytest tests/test_job_store.py -v`

### Task 2 (CP4): API + worker (fake pipeline)
Files: `app/api/schemas.py`, `app/api/routes.py`, `app/jobs/worker.py`, `app/main.py`, `app/artifacts/store.py`,
`app/generation/topics/*` (registry + resolve only), `tests/test_api.py`, `tests/test_topics.py`
- `Worker(store, runner)`: `asyncio.Queue`; `submit(job_id)`; runner is `Callable[[Job, ProgressSink], PipelineResult]`
  executed via `asyncio.to_thread` with a timeout; maps `PipelineError(code, stage, msg)` → `store.fail`.
- `create_app(settings, runner=None)` so tests inject a fake runner.
- Routes per spec §5. Verify: `uv run pytest tests/test_api.py tests/test_topics.py -v`

### Task 3 (CP5): Plan model, stub provider, plan gates
Files: `app/generation/plan.py`, `app/generation/script_provider.py`, `app/generation/validate.py`,
topic plans in `app/generation/topics/chemistry/*.py`, `tests/test_plan_gates.py`
- `ScenePlan/Scene/Segment` (extra=forbid), `plan_hash()`.
- `StubScriptProvider(faults).generate(topic, query, attempt) -> dict`.
- `validate_plan(raw, topic, renderers) -> (ScenePlan|None, problems)`.
- `plan_with_retries(provider, topic, query, renderers, sink) -> (ScenePlan, source)`.
- Verify: `uv run pytest tests/test_plan_gates.py -v`

### Task 4 (CP6): Narration
Files: `app/generation/tts.py`, `app/generation/timeline.py`, `tests/test_timeline.py`
- `Audio`, `PiperTTS` (voice loaded once), `FaultInjectingTTS`, `check_audio(audio, text)`,
  `narrate(plan, tts, sink) -> list[Audio]` (retry ×2 per segment).
- `assemble(plan, audios) -> (Audio, list[Cue])` sample-accurate pauses; `to_srt(cues)`.

### Task 5 (CP7): Rendering
Files: `app/generation/render/{style,primitives,frame,registry}.py`, `app/generation/render/scenes/*.py`,
`tests/test_render.py`
- Renderer protocol: `kind`, `actions`, `check(scene) -> list[str]`, `draw(frame, scene, reveal)`.
- Scenes: title, bullets, ph_beaker, ph_scale, atom_shells, covalent_share, molecule_examples,
  ionic_transfer, comparison_table.
- `render_video(plan, cues, total_frames, out_path)` pipes RGB frames to ffmpeg, reusing identical frames.
- Verify: `uv run python -m app.generation.render.preview <topic_id>` writes one PNG per scene.

### Task 6 (CP8): Compose, QA, pipeline, end-to-end
Files: `app/generation/compose.py`, `app/generation/qa.py`, `app/generation/pipeline.py`, `tests/test_e2e.py` (slow)
- `mux(video, audio, out)` retry ×1; `verify(mp4, expected_s) -> QAReport`.
- `Pipeline.run(job, sink) -> PipelineResult`; publishes only after QA passes.
- Verify: `uv run pytest -m slow -v`

### Task 7 (CP9): Reliability tests
- Fault paths (`plan_invalid_once`, `plan_invalid_always`, `tts_silent_always`), repeatability test.

### Task 8 (CP10): Docs + samples
- README, `docs/ARCHITECTURE.md`, `scripts/demo.sh`, `scripts/setup.sh`, `samples/` with 3 videos + queries.
