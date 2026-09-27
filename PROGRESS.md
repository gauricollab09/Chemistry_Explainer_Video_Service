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
- [x] CP7 — Rendering primitives + core scenes for all 3 topics
- [x] CP8 — Compose + QA gate + atomic publish; end-to-end for all 3 queries
- [x] CP9 — Reliability: retries, fallback, fault injection, repeatability test
- [x] CP10 — README, architecture note, samples, demo script
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

### CP7 — Rendering (2026-09-27)

**Changed:** `app/generation/render/` — `style.py` (palette, CPK atom colours, universal-indicator pH
colours, fonts), `primitives.py` (2× supersampled shapes, easing, sub/superscript chemistry text,
atoms with Lewis-style electron slots), 9 scene renderers (`title`, `bullets`, `ph_beaker`, `ph_scale`,
`atom_shells`, `covalent_share`, `molecule_examples`, `ionic_transfer`, `comparison_table`) each with a
`check()` used by the plan gate, `video.py` (frame loop → ffmpeg, redraws only when something changes,
caption bar, scene fades, progress bar; `render_stills` preview).

**Run:** `uv run python -m app.generation.render.video data/stills` (one PNG per scene), and
`uv run pytest tests/test_render.py -v`

**Results:** 54 tests pass overall. Real renderers accept all 3 reference plans and reject unknown steps,
impossible atoms (5 electrons in hydrogen) and missing params (reported, not crashed). Visual review of
the stills found two layout bugs — the log-scale headline overlapped example cards, beaker labels
collided with two-line captions — both fixed.

**Incomplete:** compose + QA + pipeline wiring verified end to end (CP8).

### CP8 — Compose, QA gate, pipeline; first end-to-end run (2026-09-27)

**Changed:** `compose.py` (ffmpeg mux, retry ×1, `compose_fail_once` fault), `qa.py` (ffprobe the final
MP4: H.264 1280×720 + AAC, duration vs timeline ± 0.5 s, 5 sampled frames non-blank, audio not silent),
`pipeline.py` (stages with timing events, manifest, atomic publish only after QA), paced animation for
list-like steps (pH examples now appear as they are named), job timeout raised to 600 s,
`scripts/demo.sh`, `scripts/setup.sh`, slow e2e tests, README + ARCHITECTURE.

**Run:**
```bash
uv run uvicorn app.main:app --port 8000
scripts/demo.sh            # or: curl -X POST localhost:8000/videos -d '{"query": "..."}'
```

**Results:** first real API run of "How does the pH scale work?" → `succeeded` in 168 s: planning 33 ms,
narrating 23 s (69.9 s speech), rendering 136 s (2318 frames, only 449 drawn), composing 4 s,
verifying 4 s; video 77.3 s, 2.1 MB, all QA checks passed. Contact sheet confirmed steps build in sync
with captions. Observed: the 300 s timeout left < 2× headroom → raised to 600 s. Piper speech length
varies slightly between runs (69.9 s vs 69.8 s) → repeatability test compares plan hash exactly and
duration within tolerance.

**Incomplete:** samples for all 3 queries (demo running), slow-suite run (CP9).

### CP9a — Visible failure paths (2026-09-27)

**Changed:** out-of-scope queries now get a learner-facing 422 message that echoes the query and lists
the supported questions; `scripts/demo_failures.sh` (own server on :8001 with
`plan_invalid_once,tts_silent_always`); README failure table; fixed overlapping Na/Cl labels found by
reviewing video contact sheets.

**Run:** `scripts/demo_failures.sh`

**Results:** out-of-scope → 422 `UNSUPPORTED_TOPIC` (no job); blank query → 422; unknown id → 404;
download while narrating → 409 `VIDEO_NOT_READY`; faulted job → `plan_rejected` then `plan_accepted`
(recovered), then 3× `tts_rejected` (rms=0) → `failed / narrating / TTS_FAILED` with the segment named.
First attempt of the script broke on macOS system Python 3.9 (backslash in f-string) — fixed.

**Incomplete:** slow suite run; samples commit; GitHub push.

### CP10 — Samples, docs, GitHub (2026-09-27)

**Changed:** final `samples/` (3 videos + captions + query/plan-hash table), README, ARCHITECTURE,
private repo https://github.com/gauricollab09/TaloTrace (history intact).

**Run:** `scripts/demo.sh` regenerates `samples/`.

**Results:** 7 real runs so far, 7 succeeded, all QA-passed. Same query → same plan hash every time;
duration spread ≤ 0.53 s per topic (Piper's sampled speech timing). Job time 100–156 s. Contact-sheet
review of the final ionic video confirms the label fix.

**Incomplete:** slow suite run; reviewers to be added as collaborators by the user.

### Bug — "ionic_vs_covalent.mp4 is blank, no narration" (2026-09-27)

**Symptom:** user reported the ionic sample showed no visuals and no audio in QuickTime.

**Investigation:** the file was valid — byte-identical to the QA-passed published artifact and to git
(sha `215d958a…`), full decode of 2652 frames with 0 errors, audio −16.7 dB. `lsof` showed QuickTime
holding it open. Timeline: user opened the *old* render at ~17:29:42; `demo.sh` overwrote the same
inode in place with `curl -o` at 17:29:43; QuickTime's parsed index then pointed at rewritten bytes
(black video, no sound), and later `open` calls only re-focused that stale window. A fresh copy at a
new path played normally.

**Root cause:** non-atomic client download in `scripts/demo.sh` (the server already publishes
atomically; the demo client did not).

**Fix:** download to `<file>.part`, then `mv` into place. Verified: re-downloading over a file held open
gives a new inode, the open handle still reads the original intact, and no `.part` is left behind.

### CP9 — Slow end-to-end suite (2026-09-27)

**Run:** `uv run pytest -m slow -v`

**Results:** 5 passed in 9 min 6 s — all 3 required queries produce QA-verified videos through the API
with real Piper + ffmpeg; the same query twice gives an identical plan hash and consistent duration;
injected faults (`plan_invalid_once` + `tts_silent_always`) are recovered (plan) and reported
(`failed / narrating / TTS_FAILED`, 3 `tts_rejected` events). Fast suite: 54 passed.

**Incomplete:** reviewer collaborator invites and the recording walkthrough (user).

### CP11 — Repeatability check + timeout demo (2026-09-27)

**Changed:** `scripts/check_repeatability.py` (compares two jobs via the public API: plan hash,
sentence-by-sentence narration, per-sentence frame pixel diff, timing drift), `scripts/demo_timeout.sh`
(server with a 25 s limit), worker logs when a timed-out job's thread stops.

**Run:** `uv run python scripts/check_repeatability.py <job_a> <job_b>`, `scripts/demo_timeout.sh`

**Results:** pH runs 13 min and 30 min apart: identical plan hash, identical 14/14 sentences, largest
frame difference 0.45/255, timing drift ≤ 0.53 s → REPEATABLE. Timeout: job A → `failed / TIMEOUT` at
its stage, download 409, `/health` answered in 4–23 ms throughout, job B started right after A failed,
A's thread logged "abandoned … nothing published", 0 files published for A. (A macOS `sed` quirk
briefly hid the demo output — not a product issue.)

**Known limitation:** a timed-out thread finishes its current step before stopping (Python threads
cannot be killed); production would run generation in a separate process/worker that can be terminated.

**Full rerun of all 3 queries vs committed samples** (`check_repeatability.py`):

| Topic | Plan hash | Narration | Largest frame diff | Duration drift | Result |
|---|---|---|---|---|---|
| ph_scale | identical | 14/14 identical | 0.45 / 255 | 0.53 s | REPEATABLE |
| covalent_bonds | identical | 14/14 identical | 0.37 / 255 | 0.64 s max per sentence | REPEATABLE |
| ionic_vs_covalent | identical | 17/17 identical | 0.47 / 255 | 0.53 s | REPEATABLE |

All 10 real generation runs to date succeeded and passed QA.

### CP12 — Documentation fact-check (2026-09-27)

**Changed:** rewrote `docs/ARCHITECTURE.md` (system blocks, request flow, lifecycle incl. step-by-step
timeout, gates table, atomic publish, video design, repeatability evidence, decisions/trade-offs,
limitations + production path) and `README.md`; refreshed `samples/README.md`.

**Verified against code and measurements:** video lengths 72.1/77.0/88.4 s (README said ~75 s); job
time 90–230 s (said 2.5–3 min); fast suite 54 tests in 12–24 s (said ~15 s); onnxruntime 1.23.2 on
Intel macOS vs 1.30.0 elsewhere (said "resolve normally"); drawn frames 20–24 % (said ~20 %); startup
recovery covers queued *and* running jobs; QA comment −17 dB (said −20 dB); background-only frame std
measured 2.79 (comment "~3" confirmed). Every file path referenced in the docs exists.
