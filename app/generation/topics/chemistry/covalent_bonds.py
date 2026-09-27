from app.generation.topics.base import TopicSpec

TOPIC = TopicSpec(
    id="covalent_bonds",
    subject="chemistry",
    title="Why Atoms Form Covalent Bonds",
    canonical_query="Why do atoms form covalent bonds?",
    match_patterns=(frozenset({"covalent"}),),
    required_terms=("outer shell", "share", "pair of electrons", "stable", "covalent bond"),
)
