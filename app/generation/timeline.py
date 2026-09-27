"""Timeline: stitches per-segment audio into one track and records when each segment plays.

Times are derived from sample counts, so visuals, captions and audio can never drift apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.generation.plan import ScenePlan

FPS = 30
PAUSE_AFTER_SEGMENT_S = 0.35
PAUSE_AFTER_SCENE_S = 0.6


@dataclass(frozen=True)
class Cue:
    scene_index: int
    segment_index: int
    start: float       # segment's visual step starts animating
    speech_end: float  # narration for this segment ends
    end: float         # next segment starts
    text: str
    show: str


def assemble(plan: ScenePlan, audios: list) -> tuple:
    """Return (narration Audio, cues, total_frames). Audio is padded to exactly total_frames / FPS."""
    from app.generation.tts import Audio

    sample_rate = audios[0].sample_rate
    if any(a.sample_rate != sample_rate for a in audios):
        raise ValueError("all narration segments must share one sample rate")

    parts: list[np.ndarray] = []
    cues: list[Cue] = []
    position = 0
    k = 0
    for scene_index, scene in enumerate(plan.scenes):
        for segment_index, segment in enumerate(scene.segments):
            audio = audios[k]
            k += 1
            last_in_scene = segment_index == len(scene.segments) - 1
            pause = round((PAUSE_AFTER_SEGMENT_S + (PAUSE_AFTER_SCENE_S if last_in_scene else 0)) * sample_rate)
            start = position
            parts += [audio.samples, np.zeros(pause, dtype=np.int16)]
            position += len(audio.samples) + pause
            cues.append(Cue(
                scene_index, segment_index,
                start=start / sample_rate,
                speech_end=(start + len(audio.samples)) / sample_rate,
                end=position / sample_rate,
                text=segment.narration, show=segment.show,
            ))

    total_frames = math.ceil(position / sample_rate * FPS)
    target = round(total_frames / FPS * sample_rate)
    parts.append(np.zeros(target - position, dtype=np.int16))
    return Audio(np.concatenate(parts), sample_rate), cues, total_frames


def to_srt(cues: list[Cue]) -> str:
    def stamp(t: float) -> str:
        ms = round(t * 1000)
        return f"{ms // 3_600_000:02}:{ms // 60_000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    return "\n".join(
        f"{i}\n{stamp(c.start)} --> {stamp(c.speech_end)}\n{c.text}\n" for i, c in enumerate(cues, start=1)
    )
