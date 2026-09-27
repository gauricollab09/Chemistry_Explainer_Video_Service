"""Artifact boundary: a scratch workspace per job, and an atomic publish step.

Files only become visible under `published/<job_id>/` once the whole set is in place, so a client can
never download a half-written video. Swapping to S3 means reimplementing this class.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


class LocalArtifactStore:
    def __init__(self, root: Path):
        self._work = root / "work"
        self._published = root / "published"
        self._work.mkdir(parents=True, exist_ok=True)
        self._published.mkdir(parents=True, exist_ok=True)

    def workspace(self, job_id: str) -> Path:
        path = self._work / job_id
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
        return path

    def publish(self, job_id: str, files: dict[str, Path]) -> Path:
        staging = self._published / f".staging-{job_id}"
        final = self._published / job_id
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        for name, src in files.items():
            shutil.copy2(src, staging / name)
        if final.exists():
            shutil.rmtree(final)
        os.replace(staging, final)  # atomic rename on the same filesystem
        shutil.rmtree(self._work / job_id, ignore_errors=True)
        return final

    def get(self, job_id: str, name: str) -> Path | None:
        path = self._published / job_id / name
        return path if path.is_file() else None
