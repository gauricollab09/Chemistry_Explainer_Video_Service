"""Compose: mux the rendered video stream with the narration track into the final MP4."""

from __future__ import annotations

import subprocess
from pathlib import Path


class ComposeError(Exception):
    pass


def mux(video: Path, narration_wav: Path, out: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video), "-i", str(narration_wav),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart", str(out),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired as e:
        raise ComposeError("ffmpeg mux timed out after 120s") from e
    if result.returncode != 0:
        raise ComposeError(f"ffmpeg exited {result.returncode}: {result.stderr.decode()[-400:]}")
