from app.generation.topics.base import TopicSpec

REFERENCE_PLAN = {
    "topic_id": "ph_scale",
    "title": "How does the pH scale work?",
    "scenes": [
        {
            "kind": "title",
            "heading": "How does the pH scale work?",
            "params": {"subtitle": "Acids, bases and hydrogen ions"},
            "segments": [
                {"show": "title", "narration": "How does the pH scale work? Let's find out what that number really measures."},
            ],
        },
        {
            "kind": "ph_beaker",
            "heading": "pH measures hydrogen ions",
            "segments": [
                {"show": "beakers", "narration": "Every water-based solution contains some hydrogen ions. The pH scale measures how many hydrogen ions are present."},
                {"show": "acid", "narration": "When a solution has lots of hydrogen ions, it is acidic, like lemon juice or vinegar."},
                {"show": "base", "narration": "When it has very few hydrogen ions, and more hydroxide ions instead, it is basic, like soap or bleach."},
            ],
        },
        {
            "kind": "ph_scale",
            "heading": "The pH scale: 0 to 14",
            "params": {
                "examples": [
                    {"label": "Lemon juice", "ph": 2},
                    {"label": "Coffee", "ph": 5},
                    {"label": "Pure water", "ph": 7},
                    {"label": "Baking soda", "ph": 9},
                    {"label": "Bleach", "ph": 13},
                ]
            },
            "segments": [
                {"show": "bar", "narration": "The pH scale runs from 0 to 14."},
                {"show": "acidic", "narration": "Anything below 7 is acidic. The lower the number, the stronger the acid."},
                {"show": "neutral", "narration": "Exactly 7 is neutral. Pure water sits right in the middle."},
                {"show": "basic", "narration": "Anything above 7 is basic, and the higher the number, the stronger the base."},
                {"show": "examples", "narration": "Lemon juice is about 2, coffee about 5, baking soda about 9, and bleach about 13."},
                {"show": "log", "narration": "Here is the surprising part: the scale is logarithmic. Each step down means ten times more hydrogen ions."},
                {"show": "hold", "narration": "So a pH of 3 is ten times more acidic than 4, and a hundred times more acidic than 5."},
            ],
        },
        {
            "kind": "bullets",
            "heading": "Key takeaways",
            "params": {
                "items": [
                    "pH measures hydrogen ion concentration",
                    "Below 7 is acidic, 7 is neutral, above 7 is basic",
                    "Each pH step is a 10× change in hydrogen ions",
                ]
            },
            "segments": [
                {"show": "item1", "narration": "To recap: pH measures the concentration of hydrogen ions in a solution."},
                {"show": "item2", "narration": "Below 7 is acidic, exactly 7 is neutral, and above 7 is basic."},
                {"show": "item3", "narration": "And because the scale is logarithmic, each step is a tenfold change."},
            ],
        },
    ],
}

TOPIC = TopicSpec(
    id="ph_scale",
    subject="chemistry",
    title="How the pH Scale Works",
    canonical_query="How does the pH scale work?",
    match_patterns=(frozenset({"ph"}),),
    required_terms=("hydrogen ions", "acidic", "basic", "neutral", "logarithmic", "0 to 14"),
    reference_plan=REFERENCE_PLAN,
)
