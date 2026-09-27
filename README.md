# TaloTrace — AI Chemistry Explainer Video Service

A FastAPI backend where a learner asks a chemistry question and gets back a 70–90-second narrated,
animated explainer video. Requests run as asynchronous jobs with an explicit lifecycle, and every video
passes content and output quality gates before it can be downloaded.

| Learner query | Topic | Sample (duration) |
|---|---|---|
| How does the pH scale work? | `ph_scale` | [`samples/ph_scale.mp4`](samples/ph_scale.mp4) (77.0 s) |
| Why do atoms form covalent bonds? | `covalent_bonds` | [`samples/covalent_bonds.mp4`](samples/covalent_bonds.mp4) (72.1 s) |
| What is the difference between ionic and covalent bonding? | `ionic_vs_covalent` | [`samples/ionic_vs_covalent.mp4`](samples/ionic_vs_covalent.mp4) (88.4 s) |

Captions, plan hashes and repeatability results: [`samples/README.md`](samples/README.md).
Design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (job lifecycle, persistence/artifact boundary,
AI/video boundary, reliability, trade-offs) · [`docs/SPEC.md`](docs/SPEC.md) (agreed design) ·
[`PROGRESS.md`](PROGRESS.md) (build log: what changed, how it was verified, what was found).

## Setup

Requires Python 3.12 via [uv](https://docs.astral.sh/uv/), and ffmpeg (`brew install ffmpeg` /
`apt install ffmpeg`).

```bash
scripts/setup.sh   # uv sync + downloads the Piper voice en_US-lessac-medium (~63 MB) into voices/
```

> `pyproject.toml` sets `tool.uv.required-environments` so the lockfile also resolves on Intel macOS:
> there it installs `onnxruntime` 1.23.2 (the newest release has no Intel-mac wheels); every other
> platform gets 1.30.0.

## Run

```bash
uv run uvicorn app.main:app --port 8000      # interactive API docs: http://localhost:8000/docs

scripts/demo.sh [base_url] [out_dir]          # submit the 3 queries, poll, download (default out_dir: samples/)
scripts/demo_failures.sh                      # ~30 s tour of the failure paths (own server on :8001)
scripts/demo_timeout.sh                       # job over a 25 s limit → TIMEOUT, queue moves on (own server on :8002)
uv run python scripts/check_repeatability.py <job_a> <job_b>   # same query twice: plan, text, frames, timing
```

A job takes roughly 1.5–3 minutes on an Intel MacBook (90–230 s measured; the top end was with other
jobs competing for CPU). The first job after startup also loads the voice model (~8 s).

Environment: `CHEMVID_DATA_DIR` (default `data/`), `CHEMVID_VOICE`, `CHEMVID_JOB_TIMEOUT_S`
(default 600), `CHEMVID_FAULTS` (fault injection, see Tests).

## API

| Method | Path | Result |
|---|---|---|
| POST | `/videos` `{"query": "..."}` | **202** job summary with `links`; **422** `UNSUPPORTED_TOPIC` or invalid query |
| GET | `/videos` | all jobs, newest first |
| GET | `/videos/{id}` | status, stage, error code/stage/message, `plan_hash`, `plan_source`, QA report, event log |
| GET | `/videos/{id}/file` | the MP4; **409** `VIDEO_NOT_READY` until the job succeeds |
| GET | `/videos/{id}/captions` | SRT captions; same rules |
| GET | `/topics` | supported topics |
| GET | `/health` | ffmpeg / ffprobe / voice model checks |

```bash
curl -s -X POST localhost:8000/videos -H 'content-type: application/json' \
     -d '{"query": "How does the pH scale work?"}'
curl -s localhost:8000/videos/<id>              # poll: queued → planning → … → succeeded
curl -s localhost:8000/videos/<id>/file -o ph.mp4
```

`status` is `queued | running | succeeded | failed`; `stage` is `queued | planning | narrating |
rendering | composing | verifying | done` (for a failed job: the stage where it stopped).

What a client sees when things go wrong:

| Situation | Response |
|---|---|
| Question outside the 3 supported topics | `422 UNSUPPORTED_TOPIC`: learner-facing message echoing the query + the supported queries; no job created |
| Query shorter than 3 or longer than 300 characters | `422` validation error |
| Unknown job id | `404 NOT_FOUND` |
| Download before the job succeeds (or after it failed) | `409 VIDEO_NOT_READY` with status, stage and error code |
| Generation fails | job `failed` with `error_code` (`PLAN_INVALID`, `TTS_FAILED`, `RENDER_FAILED`, `COMPOSE_FAILED`, `QA_FAILED`, `TIMEOUT`, `INTERRUPTED`, `INTERNAL`), `error_stage`, `error_message`, and every retry in the event log |

## Tests

```bash
uv run pytest            # 54 fast tests (~15–25 s): job store, API + worker with fake runners, topic
                         # matching, plan gates, narration timing, renderer checks, non-blank stills
uv run pytest -m slow -v # 5 tests (~9 min), real Piper + ffmpeg: 3 queries end to end,
                         # same query twice, injected faults
uv run python -m app.generation.render.video data/stills   # one PNG per scene, no TTS needed
```

Fault injection (`CHEMVID_FAULTS`, comma-separated): `plan_invalid_once` (bad plan → retried),
`plan_invalid_always` (→ curated fallback plan), `tts_silent_once` (→ sentence retried),
`tts_silent_always` (→ `failed / narrating / TTS_FAILED`), `compose_fail_once` (→ mux retried).

## Project layout

```
app/api/            HTTP routes + response schemas
app/jobs/           lifecycle model, SQLite job store, async worker
app/artifacts/      per-job workspace + atomic publish
app/generation/     pipeline, plan schema + gates, script provider, Piper TTS, timeline, compose, QA
  topics/chemistry/ the 3 topics: match patterns, required terms, curated narration + scene plans
  render/           palette, drawing primitives, 9 scene renderers, frame loop → ffmpeg
scripts/            setup, demo, failure demo, timeout demo, repeatability check
tests/              fast suite + slow end-to-end suite
```

## What was optimised for, and what was left out

- **Reliable, repeatable jobs:** explicit lifecycle and error codes, gates at every stage, retries only
  where output is non-deterministic, atomic publish after QA of the final file, restart recovery.
  Re-running each query gave the identical plan and narration, frames within 0.5/255, timing drift
  ≤ 0.64 s.
- **Educational clarity:** narration written per concept; each sentence drives one visual step (ions
  filling a beaker, the indicator scale building, an electron moving from Na to Cl, a shared pair
  forming), with captions.
- **Deliberately out of scope:** real LLM calls (the `ScriptProvider` seam is where one plugs in; its
  output would face the same gates), auth, cancellation, pagination, webhooks, multiple workers, cloud
  storage, request de-duplication.
- **Known limitations:** rendering is CPU-bound (production: parallel/dedicated render workers); a
  timed-out job's thread stops at its next checkpoint rather than immediately (production: separate
  worker process); QA checks structure, not diagram correctness. Details in
  [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#8-known-limitations-and-production-path).
