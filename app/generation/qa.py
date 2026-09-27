"""Final quality gate: inspects the finished MP4 itself, not what the pipeline believes it produced."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from app.generation.render.style import H, W

DURATION_TOLERANCE_S = 0.5
MIN_FRAME_STD = 10.0       # a background-only frame measures ~3
MIN_MEAN_VOLUME_DB = -40.0  # narration measures about -17 dB
SAMPLE_POINTS = (0.15, 0.35, 0.55, 0.75, 0.9)


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=60)


def verify(mp4: Path, expected_s: float) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}

    def record(name: str, ok: bool, detail: str) -> None:
        checks[name] = {"ok": bool(ok), "detail": detail}

    if not mp4.is_file() or mp4.stat().st_size == 0:
        record("file_exists", False, "missing or empty")
        return {"passed": False, "checks": checks}
    record("file_exists", True, f"{mp4.stat().st_size / 1e6:.1f} MB")

    probe = _run(["ffprobe", "-v", "error", "-show_entries",
                  "stream=codec_type,codec_name,width,height:format=duration", "-of", "json", str(mp4)])
    info = json.loads(probe.stdout or "{}")
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    duration = float(info.get("format", {}).get("duration", 0))

    record("video_stream", video.get("codec_name") == "h264" and (video.get("width"), video.get("height")) == (W, H),
           f"{video.get('codec_name')} {video.get('width')}x{video.get('height')}")
    record("audio_stream", audio.get("codec_name") == "aac", str(audio.get("codec_name")))
    record("duration", abs(duration - expected_s) <= DURATION_TOLERANCE_S,
           f"{duration:.2f}s (expected {expected_s:.2f}s ± {DURATION_TOLERANCE_S}s)")

    stds = []
    for fraction in SAMPLE_POINTS:
        frame = _run(["ffmpeg", "-v", "error", "-ss", f"{duration * fraction:.2f}", "-i", str(mp4),
                      "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"]).stdout
        stds.append(float(np.frombuffer(frame, dtype=np.uint8).std()) if frame else 0.0)
    record("frames_not_blank", min(stds) >= MIN_FRAME_STD, f"min pixel std {min(stds):.1f} over {len(stds)} samples")

    volume = _run(["ffmpeg", "-v", "info", "-i", str(mp4), "-af", "volumedetect", "-vn", "-f", "null", "-"])
    match = re.search(r"mean_volume:\s*(-?[\d.]+) dB", volume.stderr.decode())
    mean_db = float(match.group(1)) if match else -99.0
    record("audio_not_silent", mean_db >= MIN_MEAN_VOLUME_DB, f"mean volume {mean_db:.1f} dB")

    return {"passed": all(c["ok"] for c in checks.values()), "duration_s": round(duration, 3), "checks": checks}
