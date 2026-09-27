#!/usr/bin/env bash
# One-time setup: Python deps (uv), the Piper voice model, and a check for ffmpeg.
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync
mkdir -p voices
if [[ ! -f voices/en_US-lessac-medium.onnx ]]; then
  uv run python -m piper.download_voices --download-dir voices en_US-lessac-medium
fi
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null \
  || { echo "ffmpeg/ffprobe not found: install with 'brew install ffmpeg' or 'apt install ffmpeg'"; exit 1; }
echo "Setup complete."
