"""pH scenes: beakers of hydrogen ions, and the 0–14 indicator scale."""

from __future__ import annotations

import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from app.generation.render.primitives import (
    Frame, arrow_head, bezier, circle, ease, lerp_color, line, paste, polyline, rich, rounded, stagger, text, text_width,
)
from app.generation.render.scenes.base import Reveal, SceneRenderer
from app.generation.render.style import (
    ACCENT, GOOD, MUTED, NEGATIVE, PANEL, SS, TEXT, ph_color,
)

H_ION = (251, 146, 60)
OH_ION = NEGATIVE


def _ion(f: Frame, c, label: str, color, p: float) -> None:
    if p <= 0:
        return
    r = 19 * (0.6 + 0.4 * ease(p))
    circle(f, c, r, fill=lerp_color(color, PANEL, 0.35), outline=color, width=2, alpha=p)
    rich(f, c, label, 15, TEXT, p, bold=True)


def _scatter(seed: int, count: int, box, min_dist: float = 44) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    points: list[tuple[float, float]] = []
    x0, y0, x1, y1 = box
    while len(points) < count:
        candidate = (rng.uniform(x0, x1), rng.uniform(y0, y1))
        if all((candidate[0] - x) ** 2 + (candidate[1] - y) ** 2 >= min_dist ** 2 for x, y in points):
            points.append(candidate)
    return points


class PhBeakerScene(SceneRenderer):
    kind = "ph_beaker"
    actions = frozenset({"beakers", "acid", "base"})

    BEAKERS = (380, 900)
    TOP, BOTTOM, HALF_W = 160, 460, 150
    LIQUID_TOP = 225

    def draw_body(self, f: Frame, scene, rv: Reveal) -> None:
        shown, acid, base = rv("beakers"), rv("acid"), rv("base")
        for index, cx in enumerate(self.BEAKERS):
            tint = (lerp_color((96, 165, 250), (239, 68, 68), acid) if index == 0
                    else lerp_color((96, 165, 250), (139, 92, 246), base))
            box = (cx - self.HALF_W + 8, self.LIQUID_TOP, cx + self.HALF_W - 8, self.BOTTOM - 6)
            rounded(f, box, 22, tint, shown * 0.28)
            # glass outline: left wall, rounded base, right wall, rim lips
            rounded(f, (cx - self.HALF_W, self.TOP, cx + self.HALF_W, self.BOTTOM), 26, None, shown,
                    outline=(203, 213, 225), width=4)
            rounded(f, (cx - self.HALF_W - 4, self.TOP - 8, cx + self.HALF_W + 4, self.TOP + 12), 0,
                    (14, 22, 42), shown)
            line(f, (cx - self.HALF_W - 18, self.TOP - 4), (cx - self.HALF_W, self.TOP + 10), (203, 213, 225), 4, shown)
            line(f, (cx + self.HALF_W + 18, self.TOP - 4), (cx + self.HALF_W, self.TOP + 10), (203, 213, 225), 4, shown)

            inner = (box[0] + 26, box[1] + 30, box[2] - 26, box[3] - 26)
            points = _scatter(11 + index, 16, inner)
            # every beaker starts with a few H+ ions
            for i, pt in enumerate(points[:3]):
                _ion(f, pt, "H^+", H_ION, stagger(shown, i, 3))
            extra_p = acid if index == 0 else base
            extra = [("H^+", H_ION)] * 11 if index == 0 else [("OH^-", OH_ION)] * 10
            for i, (pt, (label, color)) in enumerate(zip(points[3:], extra)):
                _ion(f, pt, label, color, stagger(extra_p, i, len(extra)))

        self._label(f, self.BEAKERS[0], "ACIDIC", "many H^+ ions", (239, 68, 68), acid)
        self._label(f, self.BEAKERS[1], "BASIC", "few H^+, more OH^-", (167, 139, 250), base)

    def _label(self, f, cx, title, detail, color, p):
        text(f, (cx, self.BOTTOM + 34), title, 30, color, p, "mm", bold=True)
        rich(f, (cx, self.BOTTOM + 68), detail, 22, MUTED, p)


@lru_cache(maxsize=4)
def _gradient_strip(width: int, height: int) -> tuple[Image.Image, Image.Image]:
    xs = np.linspace(0, 14, width * SS)
    colors = np.array([ph_color(x) for x in xs], dtype=np.uint8)
    strip = Image.fromarray(np.repeat(colors[None, :, :], height * SS, axis=0), "RGB")
    mask = Image.new("L", strip.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, strip.size[0] - 1, strip.size[1] - 1], radius=height * SS // 2, fill=255)
    return strip, mask


class PhScaleScene(SceneRenderer):
    kind = "ph_scale"
    actions = frozenset({"bar", "acidic", "neutral", "basic", "examples", "log"})

    X0, X1, Y, BAR_H = 110, 1170, 330, 48

    def check_params(self, params, scene) -> list[str]:
        problems = []
        for ex in params.get("examples", []):
            if not ex.get("label") or not 0 <= float(ex["ph"]) <= 14:
                problems.append(f"bad example {ex!r}")
        return problems

    def x(self, ph: float) -> float:
        return self.X0 + (self.X1 - self.X0) * ph / 14

    def draw_body(self, f: Frame, scene, rv: Reveal) -> None:
        bar, log = ease(rv("bar")), ease(rv("log"))
        width = self.X1 - self.X0
        strip, mask = _gradient_strip(width, self.BAR_H)
        visible = max(1, round(width * bar * SS))
        paste(f, strip.crop((0, 0, visible, strip.size[1])), (self.X0, self.Y), mask.crop((0, 0, visible, mask.size[1])))
        for n in range(15):
            p = stagger(bar, n, 15, 0.8)
            text(f, (self.x(n), self.Y + self.BAR_H + 22), str(n), 22, TEXT if n != 7 else GOOD, p, "mm", bold=n == 7)

        self._bracket(f, 0, 6.85, "ACIDIC", "more H^+", ph_color(1.5), ease(rv("acidic")))
        self._bracket(f, 7.15, 14, "BASIC", "fewer H^+", ph_color(12.5), ease(rv("basic")))

        neutral = ease(rv("neutral"))
        if neutral > 0:
            cx = self.x(7)
            circle(f, (cx, self.Y + self.BAR_H / 2), 30, outline=TEXT, width=4, alpha=neutral)
            line(f, (cx, self.Y + self.BAR_H + 40), (cx, self.Y + self.BAR_H + 135), GOOD, 3, neutral)
            text(f, (cx, self.Y + self.BAR_H + 158), "NEUTRAL", 28, GOOD, neutral, "mm", bold=True)
            text(f, (cx, self.Y + self.BAR_H + 190), "pure water", 20, MUTED, neutral, "mm")

        examples = scene.params.get("examples", [])
        dim = 1 - 0.55 * log
        for i, ex in enumerate(examples):
            p = ease(stagger(rv("examples"), i, len(examples)))
            if p <= 0:
                continue
            cx, color = self.x(float(ex["ph"])), ph_color(float(ex["ph"]))
            card_y = 180 if i % 2 == 0 else 110
            drop = 18 * (1 - p)
            label = ex["label"]
            half = text_width(label, 19, bold=True) / 2 + 16
            rounded(f, (cx - half, card_y - drop, cx + half, card_y + 58 - drop), 12, PANEL, p * dim, outline=color, width=2)
            text(f, (cx, card_y + 20 - drop), label, 19, TEXT, p * dim, "mm", bold=True)
            text(f, (cx, card_y + 42 - drop), f"pH {ex['ph']}", 17, color, p * dim, "mm")
            line(f, (cx, card_y + 58 - drop), (cx, self.Y - 12), color, 2, p * dim * 0.8)
            arrow_head(f, (cx, self.Y - 2), (cx, self.Y - 30), color, 12, p * dim)

        if log > 0:
            text(f, (1216, 70), "Each step = 10× more hydrogen ions", 28, ACCENT, log, "rm", bold=True)
            for i, (a, b) in enumerate(((6, 5), (5, 4), (4, 3))):
                p = stagger(log, i, 3, 0.5)
                if p <= 0:
                    continue
                start, end = (self.x(a), self.Y - 6), (self.x(b), self.Y - 6)
                control = ((start[0] + end[0]) / 2, self.Y - 120)
                pts = [bezier(start, control, end, t / 24 * p) for t in range(25)]
                polyline(f, pts, ACCENT, 4, p)
                if p > 0.95:
                    arrow_head(f, pts[-1], pts[-3], ACCENT, 14, p)
                text(f, (control[0], self.Y - 82), "×10", 24, TEXT, p, "mm", bold=True)

    def _bracket(self, f, ph0, ph1, title, detail, color, p):
        if p <= 0:
            return
        x0, x1, y = self.x(ph0), self.x(ph1), self.Y + self.BAR_H + 52
        line(f, (x0, y), (x1, y), color, 3, p)
        line(f, (x0, y - 10), (x0, y), color, 3, p)
        line(f, (x1, y - 10), (x1, y), color, 3, p)
        mid = (x0 + x1) / 2
        text(f, (mid, y + 36), title, 30, color, p, "mm", bold=True)
        rich(f, (mid, y + 72), detail, 22, MUTED, p)
