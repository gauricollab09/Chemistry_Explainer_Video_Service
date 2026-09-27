"""Visual language shared by every scene: canvas size, palette, fonts."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

W, H = 1280, 720
SS = 2  # draw at 2x and downsample for anti-aliasing

BG_TOP = (14, 22, 42)
BG_BOTTOM = (8, 12, 26)
PANEL = (30, 41, 66)
TEXT = (241, 245, 249)
MUTED = (148, 163, 184)
ACCENT = (56, 189, 248)
ELECTRON = (250, 204, 21)
POSITIVE = (248, 113, 113)
NEGATIVE = (96, 165, 250)
GOOD = (74, 222, 128)

# CPK-style element colours
ATOM_COLORS = {"H": (226, 232, 240), "O": (248, 113, 113), "Cl": (74, 222, 128), "Na": (167, 139, 250)}

# Universal indicator colours along the pH scale
PH_STOPS = [
    (0, (220, 38, 38)), (2, (239, 68, 68)), (4, (249, 115, 22)), (6, (250, 204, 21)),
    (7, (34, 197, 94)), (9, (20, 184, 166)), (11, (59, 130, 246)), (14, (126, 34, 206)),
]

_FONT_CANDIDATES = {
    False: [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    True: [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
}


@lru_cache(maxsize=128)
def font(size: float, bold: bool = False) -> ImageFont.FreeTypeFont:
    """`size` is in 1x canvas pixels; the font is loaded at supersampled size."""
    px = max(1, round(size * SS))
    for path in _FONT_CANDIDATES[bold]:
        if Path(path).is_file():
            return ImageFont.truetype(path, px)
    return ImageFont.load_default(px)


def ph_color(ph: float) -> tuple[int, int, int]:
    for (p0, c0), (p1, c1) in zip(PH_STOPS, PH_STOPS[1:]):
        if ph <= p1:
            t = (ph - p0) / (p1 - p0)
            return tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
    return PH_STOPS[-1][1]
