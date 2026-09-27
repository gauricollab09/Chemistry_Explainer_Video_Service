"""Script providers: where an LLM plugs in.

A real `LLMScriptProvider` would prompt a model with the topic, its required terms and the ScenePlan
JSON schema, and return the parsed JSON. The pipeline treats whatever comes back as untrusted: it is
validated by `validate_plan` and retried / replaced with the topic's reference plan if it fails.
"""

from __future__ import annotations

import copy
from typing import Any, Protocol

from app.generation.topics.base import TopicSpec


class ScriptProvider(Protocol):
    name: str

    def generate(self, topic: TopicSpec, query: str, attempt: int) -> dict[str, Any]:
        """Return a raw (unvalidated) ScenePlan dict. `attempt` starts at 1."""
        ...


class StubScriptProvider:
    """Deterministic stand-in for an LLM: returns the topic's curated plan.

    Fault injection simulates the ways real model output goes wrong (truncated plans), so the
    validation / retry / fallback path is exercised:
      plan_invalid_once    first attempt returns a truncated plan
      plan_invalid_always  every attempt returns a truncated plan (forces fallback)
    """

    name = "stub"

    def __init__(self, faults: frozenset[str] = frozenset()):
        self._faults = faults

    def generate(self, topic: TopicSpec, query: str, attempt: int) -> dict[str, Any]:
        plan = copy.deepcopy(topic.reference_plan)
        if "plan_invalid_always" in self._faults or ("plan_invalid_once" in self._faults and attempt == 1):
            plan["scenes"] = plan["scenes"][:1]  # model stopped early: too short, key terms missing
        return plan
