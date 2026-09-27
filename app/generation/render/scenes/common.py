"""Topic-agnostic scenes: title card and takeaway bullets."""

from __future__ import annotations

from app.generation.render.primitives import (
    Frame, circle, dashed_circle, electron, ease, on_circle, rounded, stagger, text, wrap,
)
from app.generation.render.scenes.base import Reveal, SceneRenderer, check_numbered, numbered_actions
from app.generation.render.style import ACCENT, MUTED, PANEL, TEXT, W


class TitleScene(SceneRenderer):
    kind = "title"
    actions = frozenset({"title"})
    show_heading = False

    def draw_body(self, f: Frame, scene, rv: Reveal) -> None:
        p = rv("title")
        # decorative orbit motif
        center = (W - 200, 215)
        for r, a in ((70, 0.25), (120, 0.18), (170, 0.12)):
            dashed_circle(f, center, r, ACCENT, p * a * 2, width=2)
        for r, angle in ((70, 30), (120, 200), (170, 320)):
            electron(f, on_circle(center, r, angle + 40 * (1 - ease(p))), p * 0.9)
        circle(f, center, 26, fill=ACCENT, alpha=p * 0.5)

        rise = 24 * (1 - ease(p))
        text(f, (110, 230 + rise), "CHEMISTRY EXPLAINER", 22, ACCENT, p, bold=True)
        lines = wrap(scene.heading, 58, 900, bold=True)
        y = 275 + rise
        for line_text in lines:
            text(f, (110, y), line_text, 58, TEXT, p, bold=True)
            y += 70
        rounded(f, (110, y + 12, 110 + 120 * ease(p), y + 18), 3, ACCENT, p)
        subtitle = scene.params.get("subtitle", "")
        text(f, (110, y + 40), subtitle, 30, MUTED, stagger(p, 1, 2, 0.4))


class BulletsScene(SceneRenderer):
    kind = "bullets"
    actions = numbered_actions("item", 5)

    def check_params(self, params, scene) -> list[str]:
        items = params["items"]
        if not 1 <= len(items) <= 5 or not all(isinstance(i, str) and i for i in items):
            return ["items must be 1-5 non-empty strings"]
        return check_numbered(scene, "item", len(items))

    def draw_body(self, f: Frame, scene, rv: Reveal) -> None:
        items = scene.params["items"]
        top = 150
        gap = min(110, 400 / max(1, len(items)))
        for i, item in enumerate(items):
            p = ease(rv(f"item{i + 1}"))
            if p <= 0:
                continue
            y = top + i * gap
            dx = 40 * (1 - p)
            rounded(f, (100 + dx, y, 1180 + dx, y + 86), 16, PANEL, p * 0.9)
            circle(f, (148 + dx, y + 43), 24, fill=ACCENT, alpha=p)
            text(f, (148 + dx, y + 43), str(i + 1), 26, (8, 12, 26), p, "mm", bold=True)
            lines = wrap(item, 30, 950)
            size = 30 if len(lines) == 1 else 24
            for j, line_text in enumerate(wrap(item, size, 950)[:2]):
                offset = 0 if len(lines) == 1 else (j - 0.5) * 30
                text(f, (196 + dx, y + 43 + offset), line_text, size, TEXT, p, "lm")
