"""Drawing primitives. All coordinates are in 1x canvas pixels (1280×720); scaling is internal."""

from __future__ import annotations

import math
import re
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from app.generation.render.style import (
    ATOM_COLORS, BG_BOTTOM, BG_TOP, ELECTRON, H, MUTED, PANEL, SS, TEXT, W, font,
)

Color = tuple[int, int, int]
Point = tuple[float, float]


# --- maths ---------------------------------------------------------------------------------------

def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def ease(p: float) -> float:
    p = clamp(p)
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_point(a: Point, b: Point, t: float) -> Point:
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))


def lerp_color(a: Color, b: Color, t: float) -> Color:
    return tuple(round(lerp(x, y, clamp(t))) for x, y in zip(a, b))


def stagger(p: float, index: int, count: int, spread: float = 0.6) -> float:
    """Progress of item `index` when `count` items animate in one after another within p ∈ [0, 1]."""
    if count <= 1:
        return clamp(p)
    start = spread * index / (count - 1)
    return clamp((p - start) / (1 - spread))


def on_circle(center: Point, r: float, angle_deg: float) -> Point:
    a = math.radians(angle_deg)
    return (center[0] + r * math.cos(a), center[1] - r * math.sin(a))


def bezier(a: Point, control: Point, b: Point, t: float) -> Point:
    u = 1 - t
    return (u * u * a[0] + 2 * u * t * control[0] + t * t * b[0],
            u * u * a[1] + 2 * u * t * control[1] + t * t * b[1])


# --- frame ---------------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def background() -> Image.Image:
    y = np.linspace(0, 1, H * SS)[:, None]
    rows = np.array(BG_TOP) * (1 - y) + np.array(BG_BOTTOM) * y
    return Image.fromarray(np.repeat(rows[:, None, :], W * SS, axis=1).astype(np.uint8), "RGB")


class Frame:
    def __init__(self) -> None:
        self.img = background().copy()
        self.draw = ImageDraw.Draw(self.img, "RGBA")

    def finish(self) -> Image.Image:
        return self.img.reduce(SS)


def _s(v: float) -> float:
    return v * SS


def rgba(color: Color, alpha: float) -> tuple[int, int, int, int]:
    return (*color[:3], round(255 * clamp(alpha)))


# --- shapes --------------------------------------------------------------------------------------

def circle(f: Frame, c: Point, r: float, fill: Color | None = None, outline: Color | None = None,
           width: float = 2, alpha: float = 1.0) -> None:
    if alpha <= 0 or r <= 0:
        return
    box = [_s(c[0] - r), _s(c[1] - r), _s(c[0] + r), _s(c[1] + r)]
    f.draw.ellipse(box, fill=rgba(fill, alpha) if fill else None,
                   outline=rgba(outline, alpha) if outline else None, width=round(_s(width)))


def dashed_circle(f: Frame, c: Point, r: float, color: Color, alpha: float = 1.0, width: float = 2,
                  dashes: int = 40) -> None:
    if alpha <= 0:
        return
    box = [_s(c[0] - r), _s(c[1] - r), _s(c[0] + r), _s(c[1] + r)]
    step = 360 / dashes
    for i in range(dashes):
        f.draw.arc(box, i * step, i * step + step * 0.55, fill=rgba(color, alpha), width=round(_s(width)))


def line(f: Frame, a: Point, b: Point, color: Color, width: float = 3, alpha: float = 1.0) -> None:
    if alpha > 0:
        f.draw.line([_s(a[0]), _s(a[1]), _s(b[0]), _s(b[1])], fill=rgba(color, alpha), width=round(_s(width)))


def polyline(f: Frame, pts: list[Point], color: Color, width: float = 3, alpha: float = 1.0) -> None:
    if alpha > 0 and len(pts) > 1:
        f.draw.line([(_s(x), _s(y)) for x, y in pts], fill=rgba(color, alpha), width=round(_s(width)), joint="curve")


def arrow_head(f: Frame, tip: Point, direction_from: Point, color: Color, size: float = 16, alpha: float = 1.0) -> None:
    angle = math.atan2(tip[1] - direction_from[1], tip[0] - direction_from[0])
    left = (tip[0] - size * math.cos(angle - 0.45), tip[1] - size * math.sin(angle - 0.45))
    right = (tip[0] - size * math.cos(angle + 0.45), tip[1] - size * math.sin(angle + 0.45))
    f.draw.polygon([(_s(x), _s(y)) for x, y in (tip, left, right)], fill=rgba(color, alpha))


def arrow(f: Frame, a: Point, b: Point, color: Color, width: float = 4, alpha: float = 1.0, head: float = 16) -> None:
    if alpha <= 0:
        return
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    shaft_end = (b[0] - head * 0.8 * math.cos(angle), b[1] - head * 0.8 * math.sin(angle))
    line(f, a, shaft_end, color, width, alpha)
    arrow_head(f, b, a, color, head, alpha)


def rounded(f: Frame, box: tuple[float, float, float, float], radius: float, fill: Color | None,
            alpha: float = 1.0, outline: Color | None = None, width: float = 2) -> None:
    if alpha <= 0:
        return
    f.draw.rounded_rectangle([_s(v) for v in box], radius=_s(radius),
                             fill=rgba(fill, alpha) if fill else None,
                             outline=rgba(outline, alpha) if outline else None, width=round(_s(width)))


def paste(f: Frame, img: Image.Image, xy: Point, mask: Image.Image | None = None) -> None:
    f.img.paste(img, (round(_s(xy[0])), round(_s(xy[1]))), mask)


# --- text ----------------------------------------------------------------------------------------

def text(f: Frame, xy: Point, s: str, size: float, color: Color = TEXT, alpha: float = 1.0,
         anchor: str = "la", bold: bool = False) -> None:
    if alpha > 0 and s:
        f.draw.text((_s(xy[0]), _s(xy[1])), s, font=font(size, bold), fill=rgba(color, alpha), anchor=anchor)


def text_width(s: str, size: float, bold: bool = False) -> float:
    return font(size, bold).getlength(s) / SS


def wrap(s: str, size: float, max_width: float, bold: bool = False) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in s.split():
        candidate = f"{current} {word}".strip()
        if current and text_width(candidate, size, bold) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + ([current] if current else [])


_RICH = re.compile(r"(_\d+|\^\d*[+-])")


def rich_width(markup: str, size: float, bold: bool = False) -> float:
    return sum(text_width(t, size * (0.62 if k else 1), bold) for t, k in _runs(markup))


def rich(f: Frame, xy: Point, markup: str, size: float, color: Color = TEXT, alpha: float = 1.0,
         align: str = "m", bold: bool = False) -> None:
    """Text with chemistry sub/superscripts: 'H_2O', 'Na^+', 'Cl^-'. `xy` is the vertical middle."""
    if alpha <= 0:
        return
    x = xy[0] - {"l": 0, "m": 0.5, "r": 1}[align] * rich_width(markup, size, bold)
    baseline = xy[1] + size * 0.36
    for t, kind in _runs(markup):
        small = size * 0.62
        if kind is None:
            text(f, (x, baseline), t, size, color, alpha, "ls", bold)
            x += text_width(t, size, bold)
        else:
            y = baseline + size * 0.22 if kind == "sub" else baseline - size * 0.42
            text(f, (x, y), t, small, color, alpha, "ls", bold)
            x += text_width(t, small, bold)


def _runs(markup: str) -> list[tuple[str, str | None]]:
    runs = []
    for part in _RICH.split(markup):
        if not part:
            continue
        if part.startswith("_"):
            runs.append((part[1:], "sub"))
        elif part.startswith("^"):
            runs.append((part[1:].replace("-", "−"), "sup"))
        else:
            runs.append((part, None))
    return runs


# --- chemistry -----------------------------------------------------------------------------------

def electron(f: Frame, c: Point, alpha: float = 1.0, r: float = 8) -> None:
    circle(f, c, r * 2.0, fill=ELECTRON, alpha=alpha * 0.18)
    circle(f, c, r, fill=ELECTRON, alpha=alpha)


def ghost_electron(f: Frame, c: Point, alpha: float = 1.0, r: float = 8) -> None:
    dashed_circle(f, c, r + 2, ELECTRON, alpha, width=1.5, dashes=10)


def shell_slots(capacity: int, facing: float) -> list[float]:
    """Electron angles on an outer shell, in the order electrons fill them (Lewis-style pairs).

    The first slot is always next to `facing`, so a lone electron points at a bonding partner.
    """
    if capacity <= 2:
        return [facing - 14, facing + 14]
    sides = [facing, facing + 90, facing + 180, facing + 270]
    firsts = [a - 11 for a in sides]
    partners = [a + 11 for a in sides[1:] + sides[:1]]
    return firsts + partners


def atom(f: Frame, c: Point, symbol: str, shell_r: float, electrons: list[float] | None = None,
         ghosts: list[float] = (), alpha: float = 1.0, shell_color: Color = MUTED, shell_alpha: float = 1.0,
         nucleus_r: float = 36, label: str | None = None) -> None:
    """A nucleus with its element symbol, a dashed outer shell, and electrons at the given angles."""
    if alpha <= 0:
        return
    color = ATOM_COLORS.get(symbol, (148, 163, 184))
    dashed_circle(f, c, shell_r, shell_color, alpha * shell_alpha * 0.8, width=2.5)
    circle(f, c, nucleus_r + 10, fill=color, alpha=alpha * 0.12)
    circle(f, c, nucleus_r, fill=lerp_color(color, PANEL, 0.55), outline=color, width=3, alpha=alpha)
    rich(f, c, label or symbol, nucleus_r * 0.9, TEXT, alpha, bold=True)
    for angle in electrons or []:
        electron(f, on_circle(c, shell_r, angle), alpha)
    for angle in ghosts:
        ghost_electron(f, on_circle(c, shell_r, angle), alpha)
