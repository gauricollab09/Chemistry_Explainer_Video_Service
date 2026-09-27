# Sample videos

Generated through the API with `scripts/demo.sh` (pipeline version 1.0.0). Each passed the final QA
gate (H.264 1280×720 + AAC, duration check, non-blank frames, audible narration). Captions alongside.

| Learner query | Video | Captions | Duration | Plan hash |
|---|---|---|---|---|
| How does the pH scale work? | [ph_scale.mp4](ph_scale.mp4) | [srt](ph_scale.srt) | 77.0 s | `7fbcc04ac27ff0bf` |
| Why do atoms form covalent bonds? | [covalent_bonds.mp4](covalent_bonds.mp4) | [srt](covalent_bonds.srt) | 72.1 s | `a850f4425346c4e2` |
| What is the difference between ionic and covalent bonding? | [ionic_vs_covalent.mp4](ionic_vs_covalent.mp4) | [srt](ionic_vs_covalent.srt) | 88.4 s | `874f4bb35f5f429b` |

Repeatability: a fresh run of each query, compared with these samples by
`scripts/check_repeatability.py`, gave the identical plan hash and identical narration (14/14, 14/14,
17/17 sentences), frames within 0.37–0.47 / 255 at every sentence, and timing drift ≤ 0.64 s — the
drift comes from Piper's sampled speech timing, which the timeline absorbs. All 10 real generation
runs during development succeeded and passed QA.
