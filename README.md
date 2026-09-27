# TaloTrace — AI Chemistry Explainer Video Service

A FastAPI backend where a learner asks a chemistry question and gets back a ~75-second narrated,
animated explainer video. Requests run as asynchronous jobs with an explicit lifecycle; every video
passes content and output quality gates before it can be downloaded.

Supported queries (the required scope):

| Query | Topic | Sample |
|---|---|---|
| How does the pH scale work? | `ph_scale` | [`samples/ph_scale.mp4`](samples/ph_scale.mp4) |
| Why do atoms form covalent bonds? | `covalent_bonds` | [`samples/covalent_bonds.mp4`](samples/covalent_bonds.mp4) |
| What is the difference between ionic and covalent bonding? | `ionic_vs_covalent` | [`samples/ionic_vs_covalent.mp4`](samples/ionic_vs_covalent.mp4) |

Design docs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (job lifecycle, boundaries, reliability),
[`docs/SPEC.md`](docs/SPEC.md) (agreed design), [`PROGRESS.md`](PROGRESS.md) (build log with checkpoints).

## Setup

Requires [uv](https://docs.astral.sh/uv/) and ffmpeg (`brew install ffmpeg` / `apt install ffmpeg`).

```bash
scripts/setup.sh   # uv sync + downloads the Piper voice (en_US-lessac-medium, ~63 MB) into voices/
```

> `pyproject.toml` pins `tool.uv.required-environments` for Intel macOS, where the newest
> `onnxruntime` has no wheels; other platforms resolve normally.

## Run

```bash
uv run uvicorn app.main:app --port 8000
# interactive API docs: http://localhost:8000/docs
scripts/demo.sh    # submits the 3 queries, polls, saves videos + captions into samples/
scripts/demo_failures.sh   # ~30 s tour of every failure path (own server on :8001 with faults on)
```

Failure behaviour a client sees:

| Situation | Response |
|---|---|
| Question outside the 3 supported topics | `422 UNSUPPORTED_TOPIC` with a learner-facing message and the supported queries; no job created |
| Empty / >300-char query | `422` validation error |
| Unknown job id | `404 NOT_FOUND` |
| Download before the video is ready, or after failure | `409 VIDEO_NOT_READY` with current status/stage/error code |
| Generation fails | job `failed` with `error_code`, `error_stage`, `error_message`, and the event log showing every retry |

Environment variables: `CHEMVID_DATA_DIR` (default `data/`), `CHEMVID_VOICE`, `CHEMVID_JOB_TIMEOUT_S`
(default 600), `CHEMVID_FAULTS` (comma-separated fault injection, see below).

## API

| Method | Path | Result |
|---|---|---|
| POST | `/videos` `{"query": "..."}` | **202** job summary with `links`; **422** `UNSUPPORTED_TOPIC` (+ supported queries) or invalid query |
| GET | `/videos` | all jobs, newest first |
| GET | `/videos/{id}` | status, stage, error code/stage/message, `plan_hash`, `plan_source`, QA report, event log |
| GET | `/videos/{id}/file` | the MP4; **409** `VIDEO_NOT_READY` until the job succeeds |
| GET | `/videos/{id}/captions` | SRT captions; same rules |
| GET | `/topics` | supported topics |
| GET | `/health` | ffmpeg / ffprobe / voice model checks |

```bash
curl -s -X POST localhost:8000/videos -H 'content-type: application/json' \
     -d '{"query": "How does the pH scale work?"}'
curl -s localhost:8000/videos/<id>           # poll: queued → planning → … → succeeded
curl -s localhost:8000/videos/<id>/file -o ph.mp4
```

Status is `queued | running | succeeded | failed`; `stage` is `queued | planning | narrating |
rendering | composing | verifying | done`. A job takes ~2.5–3 minutes on an Intel MacBook.

## Tests

```bash
uv run pytest            # fast suite (~15 s): store, API/worker with fake runners, topics, plan gates,
                         # narration timing, renderer checks, non-blank stills
uv run pytest -m slow -v # real Piper + ffmpeg: all 3 queries end to end, repeatability, fault paths
uv run python -m app.generation.render.video data/stills   # one PNG per scene, no TTS needed
```

Fault injection for demos: `CHEMVID_FAULTS=plan_invalid_once` (bad plan → retried),
`plan_invalid_always` (→ curated fallback plan), `tts_silent_once` (→ segment retried),
`tts_silent_always` (→ `failed / narrating / TTS_FAILED`), `compose_fail_once` (→ mux retried).

## What was optimised for, and what was left out

- **Reliable, repeatable jobs:** explicit lifecycle and error codes, gates at every stage, retries only
  where output is non-deterministic, atomic publish after a QA check of the final file, restart recovery.
- **Educational clarity:** narration written per concept; each sentence drives one visual step
  (ions filling a beaker, the indicator scale building, an electron moving from Na to Cl, a shared pair
  forming), with captions.
- **Deliberately out of scope:** real LLM calls (the `ScriptProvider` seam is where one plugs in — its
  output would face the same gates), auth, cancellation, pagination, webhooks, multiple workers,
  cloud storage, request de-duplication.
- **Known limitation:** rendering is CPU-bound (~2 min per video, mostly x264 encoding + frame
  piping); a production version would render scenes in parallel or on a GPU worker.
