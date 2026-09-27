"""Plan quality gates, and the plan → retry → fallback loop.

Nothing is narrated or rendered until a plan passes every gate here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import ValidationError

from app.generation.contracts import PipelineError, ProgressSink
from app.generation.plan import Scene, ScenePlan
from app.generation.script_provider import ScriptProvider
from app.generation.topics.base import TopicSpec
from app.jobs.models import ErrorCode, Stage

# Measured for en_US-lessac-medium (PROGRESS.md, CP0).
WORDS_PER_SECOND = 3.1
SEGMENT_WORDS = (3, 40)
DURATION_S = (45.0, 120.0)
PROVIDER_ATTEMPTS = 3  # first try + 2 retries, then fall back to the reference plan


class SceneChecker(Protocol):
    def check(self, scene: Scene) -> list[str]: ...


def validate_plan(
    raw: dict[str, Any], topic: TopicSpec, renderers: Mapping[str, SceneChecker]
) -> tuple[ScenePlan | None, list[str]]:
    try:
        plan = ScenePlan.model_validate(raw)
    except ValidationError as e:
        return None, [f"schema: {'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]

    problems: list[str] = []
    if plan.topic_id != topic.id:
        problems.append(f"plan is for topic '{plan.topic_id}', expected '{topic.id}'")

    for i, scene in enumerate(plan.scenes):
        renderer = renderers.get(scene.kind)
        if renderer is None:
            problems.append(f"scene {i}: no renderer for kind '{scene.kind}'")
        else:
            problems += [f"scene {i} ({scene.kind}): {p}" for p in renderer.check(scene)]
        for j, seg in enumerate(scene.segments):
            words = len(seg.narration.split())
            if not SEGMENT_WORDS[0] <= words <= SEGMENT_WORDS[1]:
                problems.append(f"scene {i} segment {j}: {words} words, allowed {SEGMENT_WORDS[0]}-{SEGMENT_WORDS[1]}")

    estimate = estimated_duration_s(plan)
    if not DURATION_S[0] <= estimate <= DURATION_S[1]:
        problems.append(f"estimated duration {estimate:.0f}s outside {DURATION_S[0]:.0f}-{DURATION_S[1]:.0f}s")

    narration = plan.narration().lower()
    missing = [term for term in topic.required_terms if term.lower() not in narration]
    if missing:
        problems.append(f"narration is missing required terms: {missing}")

    return (plan if not problems else None), problems


def estimated_duration_s(plan: ScenePlan) -> float:
    from app.generation.timeline import PAUSE_AFTER_SCENE_S, PAUSE_AFTER_SEGMENT_S

    pauses = len(plan.segments()) * PAUSE_AFTER_SEGMENT_S + len(plan.scenes) * PAUSE_AFTER_SCENE_S
    return plan.word_count() / WORDS_PER_SECOND + pauses


def plan_with_retries(
    provider: ScriptProvider,
    topic: TopicSpec,
    query: str,
    renderers: Mapping[str, SceneChecker],
    sink: ProgressSink,
) -> tuple[ScenePlan, str]:
    """Return (plan, source) where source is 'provider' or 'fallback'. Raises PLAN_INVALID."""
    for attempt in range(1, PROVIDER_ATTEMPTS + 1):
        try:
            raw = provider.generate(topic, query, attempt)
        except Exception as e:  # provider outage / malformed response
            sink.event("plan_rejected", f"{provider.name} attempt {attempt} raised {type(e).__name__}: {e}")
            continue
        plan, problems = validate_plan(raw, topic, renderers)
        if plan is not None:
            sink.event("plan_accepted", f"{provider.name} plan passed all gates", {"attempt": attempt})
            return plan, "provider"
        sink.event(
            "plan_rejected",
            f"{provider.name} attempt {attempt} failed {len(problems)} gate(s)",
            {"attempt": attempt, "problems": problems[:10]},
        )

    plan, problems = validate_plan(topic.reference_plan, topic, renderers)
    if plan is None:
        raise PipelineError(
            ErrorCode.PLAN_INVALID, Stage.PLANNING,
            f"provider failed {PROVIDER_ATTEMPTS} attempts and the reference plan is invalid: {problems[:3]}",
        )
    sink.event("plan_fallback", "Using the topic's curated reference plan", {"after_attempts": PROVIDER_ATTEMPTS})
    return plan, "fallback"
