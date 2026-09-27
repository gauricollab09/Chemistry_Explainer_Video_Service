"""Runtime settings, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINE_VERSION = "1.0.0"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    voice_model: Path
    faults: frozenset[str] = frozenset()
    job_timeout_s: float = 300.0
    pipeline_version: str = PIPELINE_VERSION

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobs.sqlite3"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"


def load_settings() -> Settings:
    faults = os.environ.get("CHEMVID_FAULTS", "")
    return Settings(
        data_dir=Path(os.environ.get("CHEMVID_DATA_DIR", ROOT / "data")),
        voice_model=Path(os.environ.get("CHEMVID_VOICE", ROOT / "voices" / "en_US-lessac-medium.onnx")),
        faults=frozenset(f.strip() for f in faults.split(",") if f.strip()),
        job_timeout_s=float(os.environ.get("CHEMVID_JOB_TIMEOUT_S", 300)),
    )
