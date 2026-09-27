# Sample videos

Generated through the API with `scripts/demo.sh` (pipeline version 1.0.0). Each passed the final QA
gate (H.264 1280×720 + AAC, duration check, non-blank frames, audible narration). Captions alongside.

| Learner query | Video | Captions | Duration | Plan hash |
|---|---|---|---|---|
| How does the pH scale work? | [ph_scale.mp4](ph_scale.mp4) | [srt](ph_scale.srt) | 77.0 s | `7fbcc04ac27ff0bf` |
| Why do atoms form covalent bonds? | [covalent_bonds.mp4](covalent_bonds.mp4) | [srt](covalent_bonds.srt) | 72.1 s | `a850f4425346c4e2` |
| What is the difference between ionic and covalent bonding? | [ionic_vs_covalent.mp4](ionic_vs_covalent.mp4) | [srt](ionic_vs_covalent.srt) | 88.4 s | `874f4bb35f5f429b` |

Repeatability across the 7 runs made during development: 7/7 succeeded; plan hash identical for every
run of the same query; duration spread ≤ 0.53 s per topic (pH 76.97–77.27 s, covalent 71.60–72.13 s,
ionic vs covalent 88.40–88.70 s), coming from Piper's sampled speech timing, which the timeline absorbs.
