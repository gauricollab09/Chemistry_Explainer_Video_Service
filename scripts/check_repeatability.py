"""Compare two finished jobs for the same query, using only the public API.

    uv run python scripts/check_repeatability.py <job_a> <job_b> [base_url]

Checks: same topic and plan hash; identical narration text, sentence by sentence; sentence timing
drift; and the visual frame shown during each sentence (sampled 1.5 s after it starts), compared
pixel by pixel.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np

W, H = 1280, 720


def get(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        return response.read()


def parse_srt(text: str) -> list[tuple[float, str]]:
    cues = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        h, m, s, ms = map(int, re.match(r"(\d+):(\d+):(\d+),(\d+)", lines[1]).groups())
        cues.append((h * 3600 + m * 60 + s + ms / 1000, " ".join(lines[2:])))
    return cues


def frame_at(video: Path, t: float) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3)[: H - 6]  # ignore the progress bar


def main(job_a: str, job_b: str, base: str) -> int:
    jobs = [json.loads(get(f"{base}/videos/{j}")) for j in (job_a, job_b)]
    captions = [parse_srt(get(f"{base}/videos/{j}/captions").decode()) for j in (job_a, job_b)]
    a, b = jobs

    print(f"query        : {a['query']!r}  vs  {b['query']!r}")
    print(f"topic        : {a['topic_id']} / {b['topic_id']}")
    print(f"plan hash    : {a['plan_hash']} / {b['plan_hash']}  -> {'IDENTICAL' if a['plan_hash'] == b['plan_hash'] else 'DIFFERENT'}")
    print(f"QA passed    : {a['qa']['passed']} / {b['qa']['passed']}")
    print(f"duration     : {a['duration_s']:.2f}s / {b['duration_s']:.2f}s  (drift {abs(a['duration_s'] - b['duration_s']):.2f}s)")

    texts_a, texts_b = [t for _, t in captions[0]], [t for _, t in captions[1]]
    same_text = texts_a == texts_b
    print(f"narration    : {len(texts_a)} / {len(texts_b)} sentences -> {'IDENTICAL text' if same_text else 'TEXT DIFFERS'}")

    with tempfile.TemporaryDirectory() as tmp:
        videos = []
        for j in (job_a, job_b):
            path = Path(tmp) / f"{j}.mp4"
            path.write_bytes(get(f"{base}/videos/{j}/file"))
            videos.append(path)

        print("\n  #  start A  start B  drift   frame diff  sentence")
        worst = 0.0
        for i, ((start_a, text), (start_b, _)) in enumerate(zip(*captions)):
            diff = float(np.abs(frame_at(videos[0], start_a + 1.5).astype(int)
                                - frame_at(videos[1], start_b + 1.5).astype(int)).mean())
            worst = max(worst, diff)
            print(f"{i + 1:3}  {start_a:6.2f}s  {start_b:6.2f}s  {start_b - start_a:+.2f}s  {diff:8.2f}    {text[:55]}")

    print(f"\nlargest mean pixel difference: {worst:.2f} / 255 (0 = identical frame)")
    ok = a["plan_hash"] == b["plan_hash"] and same_text and worst < 2.0
    print("RESULT: " + ("REPEATABLE — same content, same visuals, small timing drift only" if ok else "NOT REPEATABLE"))
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8000"))
