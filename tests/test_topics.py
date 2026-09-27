import pytest

from app.generation.topics import default_registry


@pytest.fixture(scope="module")
def registry():
    return default_registry()


@pytest.mark.parametrize(
    "query, topic_id",
    [
        ("How does the pH scale work?", "ph_scale"),
        ("Why do atoms form covalent bonds?", "covalent_bonds"),
        ("What is the difference between ionic and covalent bonding?", "ionic_vs_covalent"),
        ("  HOW does the PH scale work??  ", "ph_scale"),
        ("ionic vs covalent?", "ionic_vs_covalent"),
        ("explain covalent bonding", "covalent_bonds"),
    ],
)
def test_resolves_supported_queries(registry, query, topic_id):
    assert registry.resolve(query).id == topic_id


@pytest.mark.parametrize("query", ["What is photosynthesis?", "Explain Newton's laws", "phosphorus"])
def test_unsupported_queries_resolve_to_none(registry, query):
    assert registry.resolve(query) is None
