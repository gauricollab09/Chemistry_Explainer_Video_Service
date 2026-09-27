from app.generation.topics.base import TopicSpec

REFERENCE_PLAN = {
    "topic_id": "ionic_vs_covalent",
    "title": "What is the difference between ionic and covalent bonding?",
    "scenes": [
        {
            "kind": "title",
            "heading": "Ionic vs covalent bonding",
            "params": {"subtitle": "Transferring electrons versus sharing them"},
            "segments": [
                {"show": "title", "narration": "What is the difference between ionic and covalent bonding? The answer is what happens to the electrons."},
            ],
        },
        {
            "kind": "ionic_transfer",
            "heading": "Ionic bonding: electrons are transferred",
            "segments": [
                {"show": "atoms", "narration": "Sodium is a metal with one outer electron. Chlorine is a non-metal with seven."},
                {"show": "transfer", "narration": "In ionic bonding, sodium transfers its outer electron to chlorine."},
                {"show": "ions", "narration": "Sodium becomes a positive ion, and chlorine becomes a negative ion. Both now have full outer shells."},
                {"show": "attract", "narration": "Opposite charges attract. That electrostatic attraction between the ions is the ionic bond."},
            ],
        },
        {
            "kind": "covalent_share",
            "heading": "Covalent bonding: electrons are shared",
            "params": {"symbol": "Cl", "valence": 7, "full": 8, "formula": "Cl_2"},
            "segments": [
                {"show": "approach", "narration": "Now compare two chlorine atoms. Each needs one more electron, and neither will give one up."},
                {"show": "overlap", "narration": "So instead of a transfer, their outer shells overlap."},
                {"show": "pair", "narration": "They share a pair of electrons between them."},
                {"show": "result", "narration": "Each chlorine atom now counts eight outer electrons. That shared pair is a covalent bond."},
            ],
        },
        {
            "kind": "comparison_table",
            "heading": "Side by side",
            "params": {
                "columns": ["Ionic", "Covalent"],
                "rows": [
                    {"label": "Electrons", "values": ["Transferred", "Shared"]},
                    {"label": "Between", "values": ["Metal + non-metal", "Non-metals"]},
                    {"label": "Forms", "values": ["Ions held by attraction", "Molecules"]},
                    {"label": "Example", "values": ["NaCl (table salt)", "H_2O, Cl_2"]},
                ],
            },
            "segments": [
                {"show": "header", "narration": "Let's put them side by side."},
                {"show": "row1", "narration": "In ionic bonds, electrons are transferred. In covalent bonds, they are shared."},
                {"show": "row2", "narration": "Ionic bonds usually form between a metal and a non-metal. Covalent bonds form between non-metals."},
                {"show": "row3", "narration": "Ionic compounds are made of charged ions held by attraction. Covalent compounds are made of molecules."},
                {"show": "row4", "narration": "Table salt is ionic, while water and chlorine gas are covalent."},
            ],
        },
        {
            "kind": "bullets",
            "heading": "Key takeaways",
            "params": {
                "items": [
                    "Ionic: electrons transfer, forming ions that attract",
                    "Covalent: non-metal atoms share pairs of electrons",
                    "Either way, atoms reach full, stable outer shells",
                ]
            },
            "segments": [
                {"show": "item1", "narration": "To recap: in an ionic bond, electrons transfer from a metal to a non-metal, and the ions attract."},
                {"show": "item2", "narration": "In a covalent bond, non-metal atoms share pairs of electrons."},
                {"show": "item3", "narration": "Either way, the atoms end up with full outer shells, which makes them more stable."},
            ],
        },
    ],
}

TOPIC = TopicSpec(
    id="ionic_vs_covalent",
    subject="chemistry",
    title="Ionic vs Covalent Bonding",
    canonical_query="What is the difference between ionic and covalent bonding?",
    match_patterns=(frozenset({"ionic", "covalent"}), frozenset({"ionic"})),
    required_terms=("transfer", "share", "ions", "metal", "ionic bond", "covalent bond"),
    reference_plan=REFERENCE_PLAN,
)
