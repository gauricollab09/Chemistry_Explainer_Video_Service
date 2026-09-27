import copy
import dataclasses

import pytest

from app.generation.contracts import PipelineError
from app.generation.script_provider import StubScriptProvider
from app.generation.topics import default_registry
from app.generation.validate import DURATION_S, estimated_duration_s, plan_with_retries, validate_plan

KINDS = [
    "title", "bullets", "ph_beaker", "ph_scale", "atom_shells", "covalent_share",
    "molecule_examples", "ionic_transfer", "comparison_table",
]


class AcceptAll:
    def check(self, scene):
        return []


PERMISSIVE = {kind: AcceptAll() for kind in KINDS}
TOPICS = default_registry().all()


class RecordingSink:
    def __init__(self):
        self.events = []

    def stage(self, stage):
        pass

    def event(self, kind, message, data=None):
        self.events.append(kind)

    def plan(self, plan_hash, plan_source):
        pass


@pytest.mark.parametrize("topic", TOPICS, ids=lambda t: t.id)
def test_reference_plans_pass_every_gate(topic):
    plan, problems = validate_plan(topic.reference_plan, topic, PERMISSIVE)
    assert problems == []
    assert DURATION_S[0] <= estimated_duration_s(plan) <= DURATION_S[1]


@pytest.mark.parametrize("topic", TOPICS, ids=lambda t: t.id)
def test_stub_output_is_repeatable(topic):
    provider = StubScriptProvider()
    first, _ = validate_plan(provider.generate(topic, topic.canonical_query, 1), topic, PERMISSIVE)
    second, _ = validate_plan(provider.generate(topic, topic.canonical_query, 1), topic, PERMISSIVE)
    assert first.plan_hash() == second.plan_hash()


def test_truncated_plan_fails_duration_and_required_terms():
    topic = TOPICS[0]
    raw = StubScriptProvider(frozenset({"plan_invalid_once"})).generate(topic, "q", attempt=1)
    plan, problems = validate_plan(raw, topic, PERMISSIVE)
    assert plan is None
    assert any("estimated duration" in p for p in problems)
    assert any("missing required terms" in p for p in problems)


def test_schema_violations_are_reported():
    topic = TOPICS[0]
    raw = copy.deepcopy(topic.reference_plan)
    raw["scenes"][1]["segments"][0].pop("narration")
    raw["unexpected"] = True
    plan, problems = validate_plan(raw, topic, PERMISSIVE)
    assert plan is None
    assert any(p.startswith("schema:") and "narration" in p for p in problems)


def test_unknown_scene_kind_and_overlong_segment_are_rejected():
    topic = TOPICS[0]
    raw = copy.deepcopy(topic.reference_plan)
    raw["scenes"][0]["kind"] = "hologram"
    raw["scenes"][1]["segments"][0]["narration"] = "word " * 41
    _, problems = validate_plan(raw, topic, PERMISSIVE)
    assert any("no renderer for kind 'hologram'" in p for p in problems)
    assert any("41 words" in p for p in problems)


def test_renderer_problems_are_surfaced():
    class Picky:
        def check(self, scene):
            return ["unknown action 'explode'"]

    topic = TOPICS[0]
    _, problems = validate_plan(topic.reference_plan, topic, {**PERMISSIVE, "title": Picky()})
    assert problems == ["scene 0 (title): unknown action 'explode'"]


def test_retry_recovers_from_one_bad_plan():
    topic, sink = TOPICS[0], RecordingSink()
    plan, source = plan_with_retries(StubScriptProvider(frozenset({"plan_invalid_once"})), topic, "q", PERMISSIVE, sink)
    assert source == "provider"
    assert sink.events == ["plan_rejected", "plan_accepted"]


def test_falls_back_to_reference_plan_when_provider_keeps_failing():
    topic, sink = TOPICS[0], RecordingSink()
    plan, source = plan_with_retries(StubScriptProvider(frozenset({"plan_invalid_always"})), topic, "q", PERMISSIVE, sink)
    assert source == "fallback"
    assert sink.events == ["plan_rejected"] * 3 + ["plan_fallback"]
    assert plan.plan_hash() == validate_plan(topic.reference_plan, topic, PERMISSIVE)[0].plan_hash()


def test_plan_invalid_when_provider_and_fallback_both_fail():
    class Broken:
        name = "broken"

        def generate(self, topic, query, attempt):
            raise TimeoutError("model timed out")

    topic = dataclasses.replace(TOPICS[0], reference_plan={"topic_id": "ph_scale", "title": "x", "scenes": []})
    with pytest.raises(PipelineError) as exc:
        plan_with_retries(Broken(), topic, "q", PERMISSIVE, RecordingSink())
    assert exc.value.code == "PLAN_INVALID"
