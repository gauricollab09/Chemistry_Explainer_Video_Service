"""ScenePlan: the structured script a provider (LLM or stub) must produce.

This is the schema an LLM would be asked to emit as JSON. Each segment is one narrated sentence plus
the visual step (`show`) that animates while it is spoken.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    narration: str
    show: str


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    heading: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    segments: list[Segment] = Field(min_length=1)


class ScenePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic_id: str
    title: str
    scenes: list[Scene] = Field(min_length=1)

    def segments(self) -> list[Segment]:
        return [seg for scene in self.scenes for seg in scene.segments]

    def narration(self) -> str:
        return " ".join(seg.narration for seg in self.segments())

    def word_count(self) -> int:
        return len(self.narration().split())

    def plan_hash(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
