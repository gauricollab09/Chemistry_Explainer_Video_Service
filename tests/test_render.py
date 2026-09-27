import copy

import numpy as np
import pytest

from app.generation.plan import ScenePlan
from app.generation.render.registry import RENDERERS
from app.generation.render.video import render_stills
from app.generation.topics import default_registry
from app.generation.validate import validate_plan

TOPICS = default_registry().all()


@pytest.mark.parametrize("topic", TOPICS, ids=lambda t: t.id)
def test_reference_plans_pass_real_renderer_checks(topic):
    _, problems = validate_plan(topic.reference_plan, topic, RENDERERS)
    assert problems == []


def test_renderer_rejects_unknown_step_and_bad_params():
    topic = default_registry().get("covalent_bonds")
    raw = copy.deepcopy(topic.reference_plan)
    raw["scenes"][2]["segments"][0]["show"] = "explode"
    raw["scenes"][1]["params"]["atoms"][0]["electrons"] = 5  # hydrogen shell only holds 2
    raw["scenes"][4]["segments"][2]["show"] = "item9"
    _, problems = validate_plan(raw, topic, RENDERERS)
    assert any("unknown visual step 'explode'" in p for p in problems)
    assert any("bad atom" in p for p in problems)
    assert any("only 3 item item(s)" in p for p in problems)


def test_renderer_reports_missing_params_instead_of_crashing():
    topic = default_registry().get("ionic_vs_covalent")
    raw = copy.deepcopy(topic.reference_plan)
    del raw["scenes"][3]["params"]["rows"]
    _, problems = validate_plan(raw, topic, RENDERERS)
    assert any("invalid params: KeyError" in p for p in problems)


@pytest.mark.parametrize("topic", TOPICS, ids=lambda t: t.id)
def test_every_scene_renders_a_non_blank_720p_frame(topic, tmp_path):
    for path in render_stills(ScenePlan.model_validate(topic.reference_plan), tmp_path):
        from PIL import Image

        pixels = np.asarray(Image.open(path).convert("L"), dtype=np.float64)
        assert pixels.shape == (720, 1280)
        assert pixels.std() > 10, f"{path.name} looks blank"
