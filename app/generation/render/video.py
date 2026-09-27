"""Frame loop: turns a validated plan + narration cues into an H.264 video stream via ffmpeg.

Frames are only redrawn when something visible changes; held frames are re-sent as bytes, which keeps
a ~75 s video to roughly a thousand actual draws.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from app.generation.plan import ScenePlan
from app.generation.render.primitives import Frame, clamp, ease, rounded, text, wrap
from app.generation.render.registry import RENDERERS
from app.generation.render.scenes.base import Reveal
from app.generation.render.style import ACCENT, H, PANEL, TEXT, W
from app.generation.timeline import FPS, Cue

ANIMATION_S = 1.0
SCENE_FADE_IN_S = 0.35
SCENE_FADE_OUT_S = 0.3
CAPTION_FADE_S = 0.2


class RenderError(Exception):
    pass


def reveal_for(scene_cues: list[Cue], active: int, progress: float) -> Reveal:
    values: dict[str, float] = {}
    for i, cue in enumerate(scene_cues[: active + 1]):
        p = 1.0 if i < active else progress
        values[cue.show] = max(values.get(cue.show, 0.0), p)
    return Reveal(values)


def draw_caption(f: Frame, caption: str, alpha: float) -> None:
    for size in (26, 23, 20):
        lines = wrap(caption, size, 1080)
        if len(lines) <= 2:
            break
    height = 34 + 34 * len(lines)
    top = 700 - height
    rounded(f, (80, top, 1200, 700 - 8), 14, PANEL, 0.88 * alpha)
    for i, line_text in enumerate(lines[:2]):
        text(f, (640, top + 30 + i * 34), line_text, size, TEXT, alpha, "mm")


def render_scene_frame(plan: ScenePlan, scene_index: int, reveal: Reveal, caption: str = "",
                       caption_alpha: float = 1.0) -> Image.Image:
    scene = plan.scenes[scene_index]
    f = Frame()
    RENDERERS[scene.kind].draw(f, scene, reveal)
    if caption:
        draw_caption(f, caption, caption_alpha)
    return f.finish()


def render_video(plan: ScenePlan, cues: list[Cue], total_frames: int, out_path: Path) -> dict:
    by_scene: dict[int, list[Cue]] = {}
    for cue in cues:
        by_scene.setdefault(cue.scene_index, []).append(cue)
    background = np.asarray(Frame().finish())

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    last_key, last_frame, draws = None, None, 0
    cue_index = 0
    try:
        for n in range(total_frames):
            t = n / FPS
            while cue_index < len(cues) - 1 and t >= cues[cue_index].end:
                cue_index += 1
            cue = cues[cue_index]
            scene_cues = by_scene[cue.scene_index]
            scene_start, scene_end = scene_cues[0].start, scene_cues[-1].end
            renderer = RENDERERS[plan.scenes[cue.scene_index].kind]
            speech = cue.speech_end - cue.start
            span = speech * 0.9 if cue.show in renderer.paced_actions else min(ANIMATION_S, max(0.3, speech))
            progress = ease((t - cue.start) / span)
            fade = clamp(min((t - scene_start) / SCENE_FADE_IN_S, (scene_end - t) / SCENE_FADE_OUT_S))
            caption_alpha = clamp((t - cue.start) / CAPTION_FADE_S)
            key = (cue_index, round(progress, 3), round(fade, 2), round(caption_alpha, 2))

            if key != last_key:
                image = render_scene_frame(plan, cue.scene_index, reveal_for(scene_cues, cue.segment_index, progress),
                                           cue.text, caption_alpha)
                frame = np.asarray(image)
                if fade < 1:
                    frame = (background * (1 - fade) + frame * fade).astype(np.uint8)
                last_key, last_frame = key, frame
                draws += 1

            out = last_frame.copy()
            bar = round(W * (n + 1) / total_frames)
            out[H - 4:, :bar] = ACCENT
            proc.stdin.write(out.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    returncode = proc.wait()
    if returncode != 0:
        raise RenderError(f"ffmpeg exited {returncode}: {proc.stderr.read().decode()[-400:]}")
    return {"frames": total_frames, "drawn_frames": draws}


def render_stills(plan: ScenePlan, out_dir: Path) -> list[Path]:
    """One PNG per scene with every step complete — a fast visual check without TTS or ffmpeg."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, scene in enumerate(plan.scenes):
        reveal = Reveal({seg.show: 1.0 for seg in scene.segments})
        path = out_dir / f"{plan.topic_id}_{i:02d}_{scene.kind}.png"
        render_scene_frame(plan, i, reveal, scene.segments[-1].narration).save(path)
        paths.append(path)
    return paths


if __name__ == "__main__":
    import sys

    from app.generation.topics import default_registry

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/stills")
    for topic in default_registry().all():
        for p in render_stills(ScenePlan.model_validate(topic.reference_plan), target):
            print(p)
