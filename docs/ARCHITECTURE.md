# Architecture

```
 client ──HTTP──▶ api/routes.py ──▶ SQLiteJobStore (jobs + job_events)
                        │                    ▲
                        │ submit(job_id)     │ stage / event / plan / succeed / fail
                        ▼                    │
                  jobs/worker.py ── asyncio.Queue ── to_thread ──▶ generation/pipeline.py
                                                                      │
      ScriptProvider ─▶ plan gates ─▶ TTSProvider ─▶ timeline ─▶ renderers ─▶ ffmpeg ─▶ QA gate
                                                                      │
                                                         LocalArtifactStore.publish (atomic)
```

## Job lifecycle

```
queued → planning → narrating → rendering → composing → verifying → succeeded
            (any active stage) ─────────────────────────────────→ failed (error_code, error_stage)
```

- `POST /videos` resolves the query to a topic *before* creating a job; unsupported queries get a 422
  listing the supported ones, so no job ever exists for work we cannot do.
- The worker pulls job ids from an in-process `asyncio.Queue` and runs the blocking pipeline in a
  thread. Every stage change and notable decision (plan rejected, TTS retry, QA report) is written to
  `job_events` and logged with the job id, so `GET /videos/{id}` is the full story of a job.
- Status transitions are enforced by the store (`queued → running → succeeded|failed`; terminal
  states are final), so a late write from an abandoned thread cannot resurrect a failed job.
- Failure modes are explicit: `PLAN_INVALID`, `TTS_FAILED`, `RENDER_FAILED`, `COMPOSE_FAILED`,
  `QA_FAILED`, `TIMEOUT` (10 min default), `INTERRUPTED` (server restarted mid-job — set on startup),
  `INTERNAL` (unexpected exception, with its message).

## Persistence and artifact boundary

- **`SQLiteJobStore`** (`app/jobs/store.py`) is the only code that knows about SQL. The API and worker
  call `create / get / list / start_stage / record_plan / succeed / fail / add_event`. Moving to
  Postgres is a new implementation of this class.
- **`LocalArtifactStore`** (`app/artifacts/store.py`) gives each job a scratch `work/<id>/` folder and
  publishes by building `published/.staging-<id>/` then renaming it into place. Clients can only ever
  see a complete set: `video.mp4`, `captions.srt`, `plan.json`, `manifest.json`. Moving to S3/GCS is a
  new implementation of `workspace / publish / get`.

## AI / video-generation boundary

The worker sees one contract (`app/generation/contracts.py`): call the runner with a job and a
progress sink; get a `PipelineResult` or a `PipelineError(code, stage, message)`.

Inside the pipeline, the two AI plug-in points are protocols:

| Seam | Today | Production |
|---|---|---|
| `ScriptProvider.generate(topic, query, attempt) -> dict` | `StubScriptProvider` returns the topic's curated plan (fault-injectable) | LLM prompted with the topic, its required terms and the ScenePlan JSON schema |
| `TTSProvider.synthesize(text) -> Audio` | `PiperTTS` (offline neural voice `en_US-lessac-medium`) | any cloud TTS |

Whatever a provider returns is treated as untrusted and gated.

## Reliability under non-determinism

| Stage | Gate | On failure |
|---|---|---|
| planning | Pydantic schema; each scene's renderer accepts its visual steps + params; 3–40 words per segment; 45–120 s estimate; topic's required terms present | re-ask ×2 → fall back to the curated reference plan (`plan_source=fallback`) → `PLAN_INVALID` |
| narrating | per segment: non-empty, RMS ≥ 200, 1.5–6 words/s | retry segment ×2 → `TTS_FAILED` |
| rendering | deterministic code — no retry | `RENDER_FAILED` |
| composing | ffmpeg exit code | retry ×1 → `COMPOSE_FAILED` |
| verifying | ffprobe on the *final file*: H.264 1280×720 + AAC, duration = timeline ± 0.5 s, 5 sampled frames not blank, audio not silent | `QA_FAILED`, never published |

Principles: retry what is non-deterministic, never retry deterministic code, verify the artifact itself
before anyone can download it.

**Repeatability.** The same query always resolves to the same topic and — via the gates — the same
validated plan (`plan_hash` recorded on every job). Timing is derived from the *actual* audio sample
counts, so Piper's small run-to-run variation in speech length shifts the animation timing with the
voice instead of desynchronising it. Fault injection (`CHEMVID_FAULTS=plan_invalid_once,
plan_invalid_always,tts_silent_once,tts_silent_always,compose_fail_once`) exercises each path.

## Video design

Each scene is a list of segments; each segment is one narrated sentence plus one visual step. The
renderer animates that step while the sentence is spoken (list-like steps are paced across the whole
sentence), with a caption bar, scene fades and a progress bar. Frames are drawn at 2× and
downsampled for anti-aliasing; unchanged frames are reused, so ~20% of frames are actually drawn.

## Adding a STEM topic

1. Add `app/generation/topics/<subject>/<topic>.py` exporting a `TopicSpec` (match patterns, required
   terms, reference plan) and register it in `default_registry()`.
2. Reuse existing scene kinds (`title`, `bullets`, `comparison_table`, `molecule_examples`, …); a new
   visual is one `SceneRenderer` subclass registered in `render/registry.py`.
No change to the API, worker, store or pipeline.
