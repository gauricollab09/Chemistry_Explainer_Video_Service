# Progress Log

Each checkpoint records: **what changed**, **how to run/test it**, **what the results tell us**, and
**what is still incomplete**.

## Checkpoints

- [x] CP0 — Environment: Python 3.12 venv, Piper + female voice, ffmpeg
- [x] CP1 — Design spec approved and committed (`docs/SPEC.md`)
- [x] CP2 — Implementation plan written (`docs/superpowers/plans/2026-09-27-chem-video-service.md`)
- [x] CP3 — Job layer: models, SQLite JobStore, startup recovery (+ tests)
- [x] CP4 — API + worker with a fake pipeline (+ tests)
- [x] CP5 — Generation: ScenePlan, topic registry, stub provider, plan gates (+ tests)
- [x] CP6 — Narration: Piper TTS per segment with gates
- [ ] CP7 — Rendering primitives + core scenes for all 3 topics
- [ ] CP8 — Compose + QA gate + atomic publish; end-to-end for all 3 queries
- [ ] CP9 — Reliability: retries, fallback, fault injection, repeatability test
- [ ] CP10 — README, architecture note, samples, demo script
- [ ] Stretch — log-scale pH scene, energy curve, electronegativity spectrum

---

### CP0 — Environment (2026-09-27)

**Changed:** `.venv` (Python 3.12 via uv); `pyproject.toml` with `piper-tts==1.8.0`; pinned
`tool.uv.required-environments` for Intel macOS (latest `onnxruntime` has no x86_64 macOS wheels →
resolved `1.23.2`); voice `en_US-lessac-medium` downloaded to `voices/`; ffmpeg/ffprobe 8.1.1 via Homebrew.

**Run:**
```bash
uv run python -m piper.download_voices --download-dir voices en_US-lessac-medium
echo "The pH scale measures how acidic or basic a solution is." \
  | uv run python -m piper -m voices/en_US-lessac-medium.onnx -f /tmp/smoke.wav
ffprobe -v error -show_entries format=duration -of csv=p=0 /tmp/smoke.wav
```

**Results:** 11 words → 3.55 s, 22.05 kHz PCM → ~3.1 words/s, so a 60–90 s video ≈ 190–280 narration
words (used for the duration gate). First install failed on `onnxruntime` platform wheels; fixed by the
platform pin.

**Incomplete:** Pillow/FastAPI not yet added; voice download to be scripted for reviewers (voices/ is
git-ignored, 63 MB).

### CP1 — Design spec (2026-09-27)

**Changed:** `docs/SPEC.md` — goals, decisions, architecture/boundaries, job lifecycle, API, video
design + storyboards, reliability gates, testing, deliverables. Git repo initialised.

**Run:** `git log --oneline` — shows the design commit as the first commit.

**Results:** Design agreed section by section (architecture → video → reliability). Failure-handling
policy is explicitly provisional; revisit when real failures appear.

**Incomplete:** user review of the written spec; then the implementation plan (CP2).

### CP2 — Implementation plan (2026-09-27)

**Changed:** condensed plan (8 tasks, interfaces, verification commands, review-focus edge cases);
added FastAPI, Uvicorn, Pillow, NumPy, pytest, httpx; pytest skips `slow` tests by default.

**Results:** "pH" pronounced correctly by Piper as written — no separate speech text needed. Voice load
takes ~7.9 s, so it is loaded once per process; synthesis ~0.6–0.9 s per sentence.

**Incomplete:** implementation (CP3+).

### CP3 — Job layer (2026-09-27)

**Changed:** `app/jobs/models.py` (JobStatus, Stage, ErrorCode, allowed transitions, Job/JobEvent),
`app/jobs/store.py` (SQLite JobStore: create/get/list, stage transitions, succeed/fail, event log,
startup recovery), `app/config.py` (env-driven settings incl. `CHEMVID_FAULTS`).

**Run:** `uv run pytest tests/test_job_store.py -v`

**Results:** 7 passed — happy-path lifecycle records 7 ordered events; failures keep code + stage +
message; terminal jobs reject further transitions; restart recovery fails only queued/running jobs
(keeps the stage they died in); state survives reopening the DB file.

**Incomplete:** nothing in the job layer; API + worker next (CP4).

### CP4 — API + worker with a fake pipeline (2026-09-27)

**Changed:** `app/generation/contracts.py` (PipelineResult / PipelineError / ProgressSink — the
worker↔generation contract), `app/jobs/worker.py` (asyncio queue, runner in a thread, timeout,
error → failed-job mapping, abandoned-thread guard), `app/artifacts/store.py` (workspace + atomic
publish), `app/generation/topics/` (deterministic query → topic matching), `app/api/` (routes +
schemas), `app/main.py` (`create_app(settings, runner)` wiring). Project renamed `talotrace`
(GitHub repo will be `TaloTrace`).

**Run:** `uv run pytest -v` (28 tests, ~12 s)

**Results:** 28 passed. Submit → 202 → poll → succeeded → download works; `/file` is 409 while running
and after failure; unsupported / empty / 301-char queries → 422 with no job created; PipelineError keeps
its code + stage; unexpected exceptions → `INTERNAL`; a slow job → `TIMEOUT` and stays failed even when
its thread wakes later; jobs orphaned by a restart → `INTERRUPTED`; messy casing/punctuation still
resolves the topic.

**Incomplete:** the real pipeline (plan → narrate → render → compose → verify) — CP5 onwards.

### CP5 — Scene plans, stub provider, plan gates (2026-09-27)

**Changed:** `app/generation/plan.py` (ScenePlan schema, `plan_hash`), `script_provider.py`
(ScriptProvider protocol + deterministic StubScriptProvider with `plan_invalid_once/always` faults),
`validate.py` (schema, renderer, 3–40 words/segment, 45–120 s estimate, required-terms gates; retry ×2
then reference-plan fallback), curated narration for all 3 topics in `topics/chemistry/*.py`.

**Run:** `uv run pytest tests/test_plan_gates.py -v`

**Results:** 13 passed. All 3 reference plans pass every gate: pH 203 words / 14 segments / ~73 s,
covalent 195 / 14 / ~71 s, ionic-vs-covalent 222 / 17 / ~81 s. Same query → same plan hash. A truncated
plan fails on duration + missing terms; one bad attempt recovers on retry; persistent failure falls back
to the reference plan (`plan_source=fallback`); provider errors + broken fallback → `PLAN_INVALID`.

**Incomplete:** renderer-specific `check()` (CP7) — tests currently use permissive checkers.

### CP6 — Narration (2026-09-27)

**Changed:** `app/generation/tts.py` (TTSProvider protocol, PiperTTS loaded once, FaultInjectingTTS
with `tts_silent_once/always`, per-segment audio gate: non-empty, RMS ≥ 200, 1.5–6 words/s; retry ×2
→ `TTS_FAILED`), `app/generation/timeline.py` (sample-accurate stitching with pauses, Cue timings,
frame-aligned padding, SRT captions).

**Run:** `uv run pytest tests/test_narration.py -v` (fake TTS), plus a real-Piper sweep over all 45
segments (script in session log).

**Results:** 5 passed. Real Piper: pH 69.0 s speech, covalent 63.7 s, ionic-vs-covalent 79.4 s; speech
rate 2.35–3.83 words/s; **0 gate failures across 45 segments**. Silent segment → retried and recovered;
always-silent → `TTS_FAILED` naming the segment. Cues are contiguous; audio length = frames / 30 exactly.

**Incomplete:** rendering (CP7).
