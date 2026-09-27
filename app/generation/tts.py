"""Text-to-speech: provider interface, Piper implementation, and the narration gate.

TTS is non-deterministic in practice (model/runtime glitches, cloud outages), so every segment is
checked before use and retried if it comes back silent, empty or implausibly short/long.
"""

from __future__ import annotations

import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from app.generation.contracts import PipelineError, ProgressSink
from app.generation.plan import ScenePlan
from app.jobs.models import ErrorCode, Stage

MIN_RMS = 200.0  # int16 speech from Piper measures ~5000
WORDS_PER_SECOND_RANGE = (1.5, 6.0)
TTS_ATTEMPTS = 3


@dataclass(frozen=True)
class Audio:
    samples: np.ndarray  # mono int16
    sample_rate: int

    @property
    def duration_s(self) -> float:
        return len(self.samples) / self.sample_rate

    def write_wav(self, path: Path) -> None:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(self.samples.astype(np.int16).tobytes())


class TTSProvider(Protocol):
    def synthesize(self, text: str) -> Audio: ...


class PiperTTS:
    """Offline neural TTS. The voice model takes ~8 s to load, so it is loaded once and reused."""

    def __init__(self, model_path: Path):
        self._model_path = model_path
        self._voice = None
        self._lock = threading.Lock()

    def synthesize(self, text: str) -> Audio:
        with self._lock:
            if self._voice is None:
                from piper import PiperVoice

                self._voice = PiperVoice.load(str(self._model_path))
            chunks = list(self._voice.synthesize(text))
        if not chunks:
            return Audio(np.zeros(0, dtype=np.int16), 22050)
        return Audio(np.concatenate([c.audio_int16_array for c in chunks]), chunks[0].sample_rate)


class FaultInjectingTTS:
    """Wraps a provider to simulate bad output: tts_silent_once / tts_silent_always."""

    def __init__(self, inner: TTSProvider, faults: frozenset[str]):
        self._inner, self._faults, self._calls = inner, faults, 0

    def synthesize(self, text: str) -> Audio:
        self._calls += 1
        audio = self._inner.synthesize(text)
        if "tts_silent_always" in self._faults or ("tts_silent_once" in self._faults and self._calls == 1):
            return Audio(np.zeros_like(audio.samples), audio.sample_rate)
        return audio


def check_audio(audio: Audio, text: str) -> list[str]:
    if len(audio.samples) == 0:
        return ["no audio returned"]
    problems = []
    rms = float(np.sqrt(np.mean(audio.samples.astype(np.float64) ** 2)))
    if rms < MIN_RMS:
        problems.append(f"audio is silent (rms={rms:.0f})")
    words_per_s = len(text.split()) / audio.duration_s
    low, high = WORDS_PER_SECOND_RANGE
    if not low <= words_per_s <= high:
        problems.append(f"implausible speech rate {words_per_s:.1f} words/s for {audio.duration_s:.2f}s")
    return problems


def narrate(plan: ScenePlan, tts: TTSProvider, sink: ProgressSink) -> list[Audio]:
    audios = []
    for index, segment in enumerate(plan.segments()):
        for attempt in range(1, TTS_ATTEMPTS + 1):
            try:
                audio = tts.synthesize(segment.narration)
                problems = check_audio(audio, segment.narration)
            except Exception as e:
                problems = [f"{type(e).__name__}: {e}"]
            if not problems:
                break
            sink.event("tts_rejected", f"segment {index} attempt {attempt}: {'; '.join(problems)}",
                       {"segment": index, "attempt": attempt})
        else:
            raise PipelineError(
                ErrorCode.TTS_FAILED, Stage.NARRATING,
                f"segment {index} failed {TTS_ATTEMPTS} attempts: {'; '.join(problems)}",
            )
        audios.append(audio)
    speech_s = sum(a.duration_s for a in audios)
    sink.event("narration_ready", f"{len(audios)} segments, {speech_s:.1f}s of speech")
    return audios
