import numpy as np
import pytest

from app.generation.contracts import PipelineError
from app.generation.plan import ScenePlan
from app.generation.timeline import FPS, PAUSE_AFTER_SCENE_S, PAUSE_AFTER_SEGMENT_S, assemble, to_srt
from app.generation.topics import default_registry
from app.generation.tts import Audio, FaultInjectingTTS, check_audio, narrate

SR = 22050


def tone(seconds: float) -> Audio:
    t = np.arange(int(seconds * SR)) / SR
    return Audio((np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16), SR)


class FakeTTS:
    """Speaks at 3 words/s as a 220 Hz tone."""

    def synthesize(self, text):
        return tone(len(text.split()) / 3.0)


class RecordingSink:
    def __init__(self):
        self.events = []

    def stage(self, stage):
        pass

    def event(self, kind, message, data=None):
        self.events.append(kind)

    def plan(self, plan_hash, plan_source):
        pass


@pytest.fixture
def plan():
    return ScenePlan.model_validate(default_registry().get("ph_scale").reference_plan)


def test_check_audio_accepts_speech_and_rejects_silence_and_bad_rates():
    assert check_audio(tone(2.0), "six words spoken at normal pace") == []
    assert any("silent" in p for p in check_audio(Audio(np.zeros(SR * 2, np.int16), SR), "six words at a normal pace"))
    assert any("implausible" in p for p in check_audio(tone(0.3), "far too many words for such a short clip"))
    assert check_audio(Audio(np.zeros(0, np.int16), SR), "anything") == ["no audio returned"]


def test_narrate_retries_a_silent_segment(plan):
    sink = RecordingSink()
    audios = narrate(plan, FaultInjectingTTS(FakeTTS(), frozenset({"tts_silent_once"})), sink)
    assert len(audios) == len(plan.segments())
    assert sink.events == ["tts_rejected", "narration_ready"]


def test_narrate_fails_with_tts_failed_after_three_attempts(plan):
    with pytest.raises(PipelineError) as exc:
        narrate(plan, FaultInjectingTTS(FakeTTS(), frozenset({"tts_silent_always"})), RecordingSink())
    assert (exc.value.code, exc.value.stage) == ("TTS_FAILED", "narrating")
    assert "segment 0 failed 3 attempts" in exc.value.message


def test_assemble_is_contiguous_and_frame_aligned(plan):
    audios = [FakeTTS().synthesize(s.narration) for s in plan.segments()]
    track, cues, total_frames = assemble(plan, audios)

    assert len(cues) == len(plan.segments())
    assert cues[0].start == 0
    for prev, cur in zip(cues, cues[1:]):
        assert cur.start == pytest.approx(prev.end)
    # scene boundaries get the extra pause
    first_scene_end = cues[0]
    assert first_scene_end.end - first_scene_end.speech_end == pytest.approx(
        PAUSE_AFTER_SEGMENT_S + PAUSE_AFTER_SCENE_S, abs=1e-3
    )
    assert track.duration_s == pytest.approx(total_frames / FPS, abs=1 / SR)
    assert total_frames / FPS >= cues[-1].end


def test_srt_uses_speech_timings(plan):
    audios = [FakeTTS().synthesize(s.narration) for s in plan.segments()]
    _, cues, _ = assemble(plan, audios)
    srt = to_srt(cues)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:04,667\nHow does the pH scale work?")
    assert f"\n{len(cues)}\n" in srt
