from app.generation.topics.base import TopicSpec

TOPIC = TopicSpec(
    id="ionic_vs_covalent",
    subject="chemistry",
    title="Ionic vs Covalent Bonding",
    canonical_query="What is the difference between ionic and covalent bonding?",
    match_patterns=(frozenset({"ionic", "covalent"}), frozenset({"ionic"})),
    required_terms=("transfer", "share", "ions", "metal", "ionic bond", "covalent bond"),
)
