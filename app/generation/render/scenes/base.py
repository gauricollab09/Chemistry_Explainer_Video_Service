"""Scene renderer contract.

A renderer draws one scene kind. Each plan segment names a visual step (`show`); while that segment is
narrated, its step animates from 0 → 1 and earlier steps stay at 1. `hold` is a no-op step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.generation.plan import Scene
from app.generation.render.primitives import Frame, rounded, text
from app.generation.render.style import ACCENT, TEXT


@dataclass(frozen=True)
class Reveal:
    progress: dict[str, float]

    def __call__(self, action: str) -> float:
        return self.progress.get(action, 0.0)


class SceneRenderer:
    kind: str = ""
    actions: frozenset[str] = frozenset()
    # Steps that list several things animate across the whole sentence instead of the first second.
    paced_actions: frozenset[str] = frozenset()
    show_heading = True

    def check(self, scene: Scene) -> list[str]:
        allowed = self.actions | {"hold"}
        problems = [f"unknown visual step '{s.show}'" for s in scene.segments if s.show not in allowed]
        try:
            problems += self.check_params(scene.params, scene)
        except (KeyError, TypeError, ValueError) as e:
            problems.append(f"invalid params: {type(e).__name__}: {e}")
        return problems

    def check_params(self, params: dict[str, Any], scene: Scene) -> list[str]:
        return []

    def draw(self, f: Frame, scene: Scene, rv: Reveal) -> None:
        if self.show_heading and scene.heading:
            text(f, (64, 44), scene.heading, 38, TEXT, bold=True)
            rounded(f, (64, 96, 144, 101), 2, ACCENT)
        self.draw_body(f, scene, rv)

    def draw_body(self, f: Frame, scene: Scene, rv: Reveal) -> None:
        raise NotImplementedError


def numbered_actions(prefix: str, count: int) -> frozenset[str]:
    return frozenset(f"{prefix}{i}" for i in range(1, count + 1))


def check_numbered(scene: Scene, prefix: str, available: int) -> list[str]:
    problems = []
    for seg in scene.segments:
        if seg.show.startswith(prefix) and seg.show[len(prefix):].isdigit():
            if int(seg.show[len(prefix):]) > available:
                problems.append(f"step '{seg.show}' but only {available} {prefix} item(s) defined")
    return problems
