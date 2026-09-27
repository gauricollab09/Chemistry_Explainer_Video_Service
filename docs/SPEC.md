# Spec — AI Chemistry Video Request Service

Status: approved design (2026-09-27). Time box: ~2 hours.

## 1. Goal and priorities

A FastAPI backend where a learner submits a chemistry question, the backend generates a short
narrated explainer video as an asynchronous job, and the client polls until the video is ready.

Priorities, in order:
1. **Clear, repeatable job handling** — explicit lifecycle, understandable failures, same query → same result.
2. **Educational content quality** — correct, coherent, visibly tied to the query; visuals synced to narration.
3. **Clear implementation** — small units with one purpose each and obvious boundaries.

Required queries (the full supported scope):
- `How does the pH scale work?`
- `Why do atoms form covalent bonds?`
- `What is the difference between ionic and covalent bonding?`

Other STEM topics must be addable by registering a new topic module — no pipeline changes.

## 2. Key decisions

| Decision | Choice | Why |
|---|---|---|
| Script / scene plan | Hand-authored per-topic plans behind a `ScriptProvider` interface; `StubScriptProvider` is the only implementation | Deterministic, correct content; the seam shows where a real LLM plugs in |
| Visuals | Pillow-drawn frames, ffmpeg assembly | Full control, fast, reliable install; Manim rejected for setup risk |
| Narration | Piper TTS, voice `en_US-lessac-medium` (female) | Natural offline voice; Google TTS rejected as unrealistic |
| Job execution | In-process `asyncio.Queue`, single worker, blocking work via `asyncio.to_thread` | Simple, observable; swap point for Celery/cloud queue |
| Persistence | SQLite behind a `JobStore` interface | Industry-standard, survives restarts |
| Artifacts | Local folder per job behind an `ArtifactStore` interface | Swap point for S3/GCS |
| Runtime | Python 3.12, uv, `pyproject.toml` | — |

Deliberately out of scope: auth, cancellation, pagination, webhooks, cloud storage, multiple workers,
request de-duplication/caching, real LLM calls, frontend.

## 3. Architecture

```
app/
  main.py                FastAPI app; lifespan starts worker + runs startup recovery
  config.py              paths, voice, pipeline_version, fault flags
  api/                   HTTP only — routes + pydantic schemas
  jobs/                  Job model, JobStatus/Stage enums, JobStore (SQLite), worker
  artifacts/             ArtifactStore (local dir per job, atomic publish)
  generation/            AI/video-generation boundary
    topics/              registry: query -> TopicSpec; chemistry/{ph_scale,covalent_bonds,ionic_vs_covalent}.py
    script_provider.py   ScriptProvider protocol + StubScriptProvider (with fault injection)
    plan.py              ScenePlan / Scene / Segment models
    validate.py          plan quality gates
    tts.py               TTSProvider protocol + PiperTTS
    render/              drawing primitives + scene renderers
    compose.py           ffmpeg: frames + audio -> mp4
    qa.py                final output verification
    pipeline.py          stage orchestration with retries
```

Boundaries:
- **Persistence boundary** — `JobStore` (create/get/list/transition/add_event). Only the worker and API touch it.
- **Artifact boundary** — `ArtifactStore` (workspace for a job, publish, path to published file).
- **Generation boundary** — `pipeline.run(job_id, topic) -> PipelineResult`; knows nothing about HTTP or SQLite.
  Providers (`ScriptProvider`, `TTSProvider`) are the plug-in points for real AI services.

## 4. Job lifecycle

```
queued → planning → narrating → rendering → composing → verifying → succeeded
            (any active stage) ─────────────────────────────────→ failed
```

- `status`: `queued | running | succeeded | failed`; `stage`: the current/last stage.
- A failed job records `error_code`, `error_stage`, human-readable `error_message`, and attempt counts.
- Each job has a timestamped event log (stage transitions, retries, gate results).
- On startup, any job left `queued`/`running` is marked `failed` with `INTERRUPTED`.
- Unsupported queries are rejected at submit time (422 + supported topics); no job is created.
- Every job records `plan_hash`, `plan_source` (`provider|fallback`), and `pipeline_version`.

Error codes: `PLAN_INVALID`, `TTS_FAILED`, `RENDER_FAILED`, `COMPOSE_FAILED`, `QA_FAILED`, `TIMEOUT`,
`INTERRUPTED`, `INTERNAL`.

## 5. API

| Method | Path | Result |
|---|---|---|
| POST | `/videos` `{"query": str}` | 202 `{id, status, stage, topic_id, links}`; 422 if unsupported |
| GET | `/videos` | list of jobs (newest first) with status/stage |
| GET | `/videos/{id}` | full job: status, stage, error, plan_hash, events, QA report, links; 404 if unknown |
| GET | `/videos/{id}/file` | `video/mp4`; 409 if not succeeded; 404 if unknown |
| GET | `/videos/{id}/captions` | `captions.srt`; same rules as `/file` |
| GET | `/topics` | supported topics with their canonical queries |
| GET | `/health` | liveness + dependency check (ffmpeg, voice model present) |

## 6. Video design

- 1280×720, 30 fps, H.264 + AAC, target 60–90 s (~190–280 narration words at Piper's ~3.1 words/s).
- Dark background; universal-indicator colours for pH (red → green → purple); CPK atom colours
  (H white, Cl green, Na purple, O red); caption bar showing the current sentence.
- **Narration–visual sync:** each scene is a list of segments; each segment = one narration sentence +
  one visual step. Each segment is synthesised separately, so its audio duration exactly defines when
  its visual step animates.
- Reusable primitives: `Atom`, `ElectronDot`, `Arrow`, `GradientBar`, `Beaker`, `CaptionBar`,
  `TitleCard`, `BulletList`; easing tweens for fades/slides/electron motion.

Storyboards (core first; *stretch* only if time allows):

| pH scale | Why covalent bonds? | Ionic vs covalent |
|---|---|---|
| Title | Title | Title |
| pH measures H⁺ concentration — beaker fills with ions | Atoms seek a full outer shell — H has 1 e⁻, room for 2 | Ionic: Na's electron moves to Cl → Na⁺ / Cl⁻ attract |
| 0–14 gradient bar; lemon 2, coffee 5, water 7, baking soda 9, bleach 13; sliding marker | Two H atoms approach, shells overlap, shared pair between them | Covalent: two Cl atoms share a pair |
| *Stretch:* logarithmic — pH 3/4/5 as 1000×/100×/10× blocks | *Stretch:* energy-vs-distance curve, ball settles at minimum | *Stretch:* electronegativity spectrum |
| Summary (3 takeaways) | Examples: H₂, H₂O, Cl₂ | Comparison table: transfer vs share, metal+non-metal vs non-metals, NaCl vs H₂O |
| | Summary | Summary |

## 7. Reliability

Principle: **retry what is non-deterministic, never retry deterministic code, and verify the output
before anything reaches the learner.** The pipeline writes to a temp workspace and publishes only after
QA passes. This is the initial policy; it will be revisited as real failures are encountered.

| Stage | Gate | On failure |
|---|---|---|
| planning | renderer exists per scene + params valid; 3–40 words/segment; estimated 45–120 s; topic's required terms present | re-ask provider ×2, then fall back to the topic's reference plan (`plan_source=fallback`) |
| narrating | per segment: wav exists, not silent, duration plausible for word count (1.5–6 words/s) | retry segment ×2 → `TTS_FAILED` |
| rendering | — (deterministic) | `RENDER_FAILED`, no retry |
| composing | ffmpeg exit code | retry ×1 → `COMPOSE_FAILED` |
| verifying | ffprobe: h264 + aac, 1280×720, duration = Σ segments ± 0.5 s; sampled frames non-blank; audio not silent | `QA_FAILED`, never published |
| whole job | 5-minute timeout | `TIMEOUT` |

Fault injection via `CHEMVID_FAULTS` (e.g. `plan_invalid_once`, `tts_silent_always`) exercises each path.

Artifacts per job: `video.mp4`, `captions.srt`, `plan.json`, `manifest.json` (plan_hash, pipeline_version,
segment timings, QA report, plan_source).

Observability: structured log lines with `job_id`, `stage`, `attempt`, `duration_ms`; per-job event log in
SQLite surfaced through `GET /videos/{id}`.

## 8. Testing

- **Fast (default):** topic resolution (3 queries, paraphrases, unsupported); plan gates (each fault
  caught with the right reason); JobStore transitions + startup recovery; API with a fake pipeline
  (202/404/409/422).
- **Slow (`-m slow`):** all 3 queries end-to-end with QA passing; **repeatability** — same query twice →
  identical plan_hash and scene count, duration within 0.1 s; fault paths (`plan_invalid_once` recovers
  with a retry event, `tts_silent_always` → `failed / narrating / TTS_FAILED`).
- **Demo:** `scripts/demo.sh` submits the 3 queries via curl, polls, downloads the videos.

## 9. Deliverables checklist

- Private GitHub repo with commit history; README (setup/run/API/tests); architecture note
  (job lifecycle, persistence/artifact boundary, AI/video boundary); the 3 best videos + their queries
  in `samples/`; no `.venv`, `voices/`, or runtime data committed.
- Screen + face recording ending with a walkthrough of the three concepts.
