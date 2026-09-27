# Architecture

A learner's question becomes an asynchronous job; the job runs a generation pipeline whose every
stage is gated; the finished video is published atomically only after the final file itself passes QA.

## 1. System blocks

```
                     ┌──────────────────────────── FastAPI process ─────────────────────────────┐
 client              │                                                                           │
 (curl, demo.sh) ──▶ │  API layer (app/api)        validate query → resolve topic → create job   │
                     │   POST /videos · GET /videos[/{id}] · /file · /captions · /topics · /health│
                     │        │ create / read                            ▲ serve published files │
                     │        ▼                                          │                       │
                     │  ┌──────────────┐  stage · event · plan   ┌───────┴──────┐                │
                     │  │ SQLiteJobStore│◀──── succeed · fail ────│    Worker    │ asyncio.Queue, │
                     │  │ jobs +        │                         │  (app/jobs)  │ 1 consumer,    │
                     │  │ job_events    │  PERSISTENCE BOUNDARY   └──────┬───────┘ job timeout    │
                     │  └──────────────┘                                │ to_thread(runner(job, sink))
                     │                                                  ▼                       │
                     │  ╔═════════════ GENERATION BOUNDARY (app/generation) ══════════════════╗  │
                     │  ║  plan ──▶ narrate ──▶ render ──▶ compose ──▶ verify ──▶ publish     ║  │
                     │  ║   │ ScriptProvider  │ TTSProvider  │ Pillow      │ ffmpeg  │ QA gate  ║  │
                     │  ║   │ (stub → LLM)    │ (Piper)      │ renderers   │ mux     │          ║  │
                     │  ╚═══╪══════════════════════════════════════════════════════════╪══════════╝  │
                     │      └── provider output is untrusted: gated before use          │           │
                     │                                                                   ▼           │
                     │  ┌────────────────────┐  ARTIFACT BOUNDARY                                    │
                     │  │ LocalArtifactStore │  work/<id>/  ──(atomic rename)──▶  published/<id>/    │
                     │  └────────────────────┘                                                       │
                     └───────────────────────────────────────────────────────────────────────────────┘
```

| Boundary | Interface | Today | Production swap |
|---|---|---|---|
| Persistence | `SQLiteJobStore` (`app/jobs/store.py`): `create / get / list / start_stage / record_plan / succeed / fail / add_event / recover_interrupted` | SQLite file | Postgres — same methods |
| Artifacts | `LocalArtifactStore` (`app/artifacts/store.py`): `workspace / publish / get` | local folders, publish by directory rename | S3/GCS + signed URLs |
| Execution | `Runner(job, sink) -> PipelineResult` or raises `PipelineError(code, stage, message)` (`app/generation/contracts.py`) | in-process thread | Celery / Cloud Tasks worker process |
| AI: script | `ScriptProvider.generate(topic, query, attempt) -> dict` | `StubScriptProvider` (curated plan, fault-injectable) | LLM prompted with topic, required terms and the ScenePlan JSON schema |
| AI: voice | `TTSProvider.synthesize(text) -> Audio` | `PiperTTS`, offline voice `en_US-lessac-medium` | any cloud TTS |

The worker knows nothing about LLMs, TTS or ffmpeg; the pipeline knows nothing about HTTP or SQL.

## 2. Request flow

```
POST /videos {"query"}
  ├─ 3–300 chars after trimming?            no → 422 (validation)
  ├─ resolves to exactly one topic?         no → 422 UNSUPPORTED_TOPIC + supported queries (no job created)
  └─ create job (queued) → worker.submit → 202 {id, status, links}

GET /videos/{id}          → status, stage, error, plan_hash, plan_source, QA report, full event log
GET /videos/{id}/file     → 409 VIDEO_NOT_READY until succeeded; then the MP4
```

Topic resolution is deterministic keyword matching (`app/generation/topics/base.py`): the most specific
pattern wins, and a tie between topics is treated as unsupported rather than guessed.

## 3. Job lifecycle

```
            ┌──────────────── any active stage: PipelineError · TIMEOUT · crash ───────────────┐
            │                                                                                  ▼
queued ─▶ planning ─▶ narrating ─▶ rendering ─▶ composing ─▶ verifying ─▶ succeeded      failed
   │                                                                                  {error_code,
   └──────────── server restarted before the job finished (set at startup) ──────────▶ error_stage,
                                                                                        error_message}
```

- `status` ∈ `queued | running | succeeded | failed`; `stage` records where the job is or where it
  stopped. Allowed status transitions are enforced by the store; `succeeded` and `failed` are final.
- Every stage change, retry and gate result is appended to `job_events` and logged as
  `job=<id> stage=<stage> <kind>: <message>`, so `GET /videos/{id}` is the complete story of a job.
- Error codes: `PLAN_INVALID`, `TTS_FAILED`, `RENDER_FAILED`, `COMPOSE_FAILED`, `QA_FAILED`,
  `TIMEOUT` (default 600 s, `CHEMVID_JOB_TIMEOUT_S`), `INTERRUPTED` (queued/running jobs found at
  startup), `INTERNAL` (unexpected exception, message included).

**Timeout, step by step.** The worker stops waiting and marks the job `failed / TIMEOUT` at its current
stage, then takes the next job from the queue. The pipeline thread cannot be killed, so it runs until
its next progress report, where the sink raises `JobAbandoned`; it logs
`abandoned after timeout … nothing published` and exits before composing or publishing. Even a late
write would be rejected, because `failed` is terminal.

## 4. Generation pipeline and gates

```
ScriptProvider ─▶ PLAN GATE ─▶ Piper per sentence ─▶ AUDIO GATE ─▶ timeline ─▶ render ─▶ mux ─▶ QA GATE ─▶ publish
```

| Stage | Gate | On failure |
|---|---|---|
| planning | Pydantic schema (extra fields forbidden); every scene's renderer accepts its visual steps and params; 3–40 words per sentence; estimated 45–120 s; topic's required terms present in the narration | re-ask provider ×2 → curated reference plan (`plan_source=fallback`) → `PLAN_INVALID` |
| narrating | per sentence: audio not empty, RMS ≥ 200 (speech ≈ 5000), 1.5–6 words/s | retry that sentence ×2 → `TTS_FAILED` |
| rendering | deterministic code | no retry → `RENDER_FAILED` |
| composing | ffmpeg exit code | retry ×1 → `COMPOSE_FAILED` |
| verifying | ffprobe the **final MP4**: H.264 1280×720 + AAC; duration = timeline ± 0.5 s; 5 sampled frames not blank (pixel std ≥ 10); mean volume ≥ −40 dB | `QA_FAILED`, never published |

Principles: **retry what is non-deterministic, never retry deterministic code, verify the artifact itself
before anyone can download it.** Fault injection (`CHEMVID_FAULTS` = `plan_invalid_once`,
`plan_invalid_always`, `tts_silent_once`, `tts_silent_always`, `compose_fail_once`) exercises each path.

**Atomic publish.** Work happens in `work/<id>/`. After QA passes, `video.mp4`, `captions.srt`,
`plan.json` and `manifest.json` are copied to `published/.staging-<id>/`, which is renamed to
`published/<id>/` in one step. Failed jobs keep their `work/<id>/` for debugging and publish nothing.

## 5. Video design

- A plan is scenes → segments; **each segment is one narrated sentence plus one visual step** (`show`).
- Each sentence is synthesised separately, so its exact audio length is known. The timeline is built
  from audio sample counts (0.35 s pause after a sentence, 0.6 s after a scene) and the video is padded
  to a whole number of frames — visuals, captions and voice cannot drift apart.
- A step animates over its first second (list-like steps, e.g. pH examples, are paced across the whole
  sentence); earlier steps in the scene stay visible. Scenes fade in and out; a caption bar shows the
  current sentence; a thin bar shows progress.
- 9 scene renderers (`title`, `bullets`, `ph_beaker`, `ph_scale`, `atom_shells`, `covalent_share`,
  `molecule_examples`, `ionic_transfer`, `comparison_table`) share one palette (universal-indicator pH
  colours, CPK atom colours) and drawing primitives (atoms with Lewis-style electron slots, chemistry
  sub/superscripts). Frames are drawn at 2× and downsampled; unchanged frames are reused, so only
  20–24 % of frames are actually drawn.

## 6. Repeatability — how and evidence

Same query → same topic → same validated plan (`plan_hash` on every job) → same visuals at every
sentence. The only run-to-run variation is Piper's sampled speech timing, which the timeline absorbs.
Measured with `scripts/check_repeatability.py` (fresh run vs committed sample):

| Topic | Plan hash | Narration | Largest frame difference | Timing drift |
|---|---|---|---|---|
| ph_scale | identical | 14/14 sentences identical | 0.45 / 255 | ≤ 0.53 s |
| covalent_bonds | identical | 14/14 identical | 0.37 / 255 | ≤ 0.64 s |
| ionic_vs_covalent | identical | 17/17 identical | 0.47 / 255 | ≤ 0.53 s |

All 10 real generation runs during development succeeded and passed QA.

## 7. Key decisions and trade-offs

| Decision | Why | Trade-off |
|---|---|---|
| Curated plans behind a stub `ScriptProvider` | correct, repeatable content; the seam shows where an LLM plugs in and what gates its output | no live generation — gates proven with fault injection, not real LLM output |
| One sentence ↔ one visual step | narration and visuals always in sync; timing from real audio | less freedom for animations spanning several sentences |
| Pillow + ffmpeg (not Manim) | light install, deterministic, full control | hand-built primitives, less polish than Manim |
| Piper, offline | natural voice, free, no network dependency | ~8 s voice load; ±0.5 s timing variation |
| SQLite behind an interface | survives restarts; standard | single machine |
| In-process queue, 1 worker, thread | simple, observable, clear swap point | no horizontal scale; a timed-out thread stops only at its next checkpoint |
| Fixed topics, keyword matching | predictable; out-of-scope rejected before any work | paraphrases need a pattern added |

## 8. Known limitations and production path

1. **No real LLM.** Production: an `LLMScriptProvider` returning JSON that passes the same plan gates,
   with the curated plan kept as fallback.
2. **Rendering is CPU-bound** — 90–230 s per job on an Intel MacBook, mostly x264 encoding and frame
   piping. Production: render scenes in parallel / on dedicated render workers.
3. **Timeouts cannot kill the thread.** Production: run generation in a separate process that can be
   terminated.
4. **One worker** — jobs run one at a time. Production: a real queue with N workers.
5. **QA is structural**, not semantic: it proves frames are not blank and audio is audible, not that the
   diagram is right. Covered today by per-scene stills (`render_stills`) and human review of frame
   contact sheets, which caught two layout bugs and an overlapping-label bug.
6. Out of scope by choice: auth, cancellation, pagination, webhooks, cloud storage, de-duplication.

## 9. Adding a STEM topic

1. Add `app/generation/topics/<subject>/<topic>.py` exporting a `TopicSpec` (match patterns, required
   terms, reference plan) and register it in `default_registry()`.
2. Reuse existing scene kinds (`title`, `bullets`, `comparison_table`, `molecule_examples`, …); a new
   visual is one `SceneRenderer` subclass registered in `app/generation/render/registry.py`.

No change to the API, worker, store or pipeline.
