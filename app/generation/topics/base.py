"""Topic registry: maps a free-text learner query to a supported topic, deterministically.

Adding a STEM topic = one new module exporting a TopicSpec, registered in `default_registry()`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


@dataclass(frozen=True)
class TopicSpec:
    id: str
    subject: str
    title: str
    canonical_query: str
    # A query matches a pattern when it contains every word in it; the most specific match wins.
    match_patterns: tuple[frozenset[str], ...]
    # Content-correctness gate: the narration must mention each of these.
    required_terms: tuple[str, ...] = ()
    # Curated plan: what the stub provider returns, and the fallback when a provider's plan fails.
    reference_plan: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def match_score(self, tokens: set[str]) -> int:
        return max((len(p) for p in self.match_patterns if p <= tokens), default=0)


class TopicRegistry:
    def __init__(self, topics: list[TopicSpec]):
        self._topics = {t.id: t for t in topics}

    def all(self) -> list[TopicSpec]:
        return list(self._topics.values())

    def get(self, topic_id: str) -> TopicSpec:
        return self._topics[topic_id]

    def resolve(self, query: str) -> TopicSpec | None:
        tokens = tokenize(query)
        scored = sorted(((t.match_score(tokens), t.id) for t in self._topics.values()), reverse=True)
        best_score, best_id = scored[0]
        if best_score == 0 or (len(scored) > 1 and scored[1][0] == best_score):
            return None  # no match, or ambiguous between two topics
        return self._topics[best_id]


def default_registry() -> TopicRegistry:
    from app.generation.topics.chemistry import covalent_bonds, ionic_vs_covalent, ph_scale

    return TopicRegistry([ph_scale.TOPIC, covalent_bonds.TOPIC, ionic_vs_covalent.TOPIC])
