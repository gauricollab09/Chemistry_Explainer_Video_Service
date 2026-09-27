# Progress Log

Each checkpoint records: **what changed**, **how to run/test it**, **what the results tell us**, and
**what is still incomplete**.

## Checkpoints

- [x] CP0 — Environment: Python 3.12 venv, Piper + female voice, ffmpeg
- [x] CP1 — Design spec approved and committed (`docs/SPEC.md`)
- [ ] CP2 — Implementation plan written
- [ ] CP3 — Job layer: models, SQLite JobStore, startup recovery (+ tests)
- [ ] CP4 — API + worker with a fake pipeline (+ tests)
- [ ] CP5 — Generation: ScenePlan, topic registry, stub provider, plan gates (+ tests)
- [ ] CP6 — Narration: Piper TTS per segment with gates
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
