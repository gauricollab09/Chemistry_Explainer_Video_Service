from app.generation.topics.base import TopicSpec

TOPIC = TopicSpec(
    id="ph_scale",
    subject="chemistry",
    title="How the pH Scale Works",
    canonical_query="How does the pH scale work?",
    match_patterns=(frozenset({"ph"}),),
    required_terms=("hydrogen ions", "acidic", "basic", "neutral", "logarithmic", "0 to 14"),
)
