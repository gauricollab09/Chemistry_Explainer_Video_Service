from app.generation.topics.base import TopicSpec

REFERENCE_PLAN = {
    "topic_id": "covalent_bonds",
    "title": "Why do atoms form covalent bonds?",
    "scenes": [
        {
            "kind": "title",
            "heading": "Why do atoms form covalent bonds?",
            "params": {"subtitle": "Sharing electrons to become stable"},
            "segments": [
                {"show": "title", "narration": "Why do atoms form covalent bonds? It all comes down to electrons, and to stability."},
            ],
        },
        {
            "kind": "atom_shells",
            "heading": "Atoms want a full outer shell",
            "params": {
                "atoms": [
                    {"symbol": "H", "name": "Hydrogen", "electrons": 1, "capacity": 2},
                    {"symbol": "Cl", "name": "Chlorine", "electrons": 7, "capacity": 8},
                ]
            },
            "segments": [
                {"show": "atom1", "narration": "An atom is most stable when its outer shell of electrons is full. Hydrogen has one electron, but its shell has room for two."},
                {"show": "atom2", "narration": "Chlorine has seven outer electrons, but its shell holds eight."},
                {"show": "slots", "narration": "Each of these atoms is one electron short of a full, stable outer shell."},
            ],
        },
        {
            "kind": "covalent_share",
            "heading": "Sharing a pair of electrons",
            "params": {"symbol": "H", "valence": 1, "full": 2, "formula": "H_2"},
            "segments": [
                {"show": "approach", "narration": "When two hydrogen atoms come close together, something useful can happen."},
                {"show": "overlap", "narration": "Their outer shells overlap, so electrons can be shared between both atoms."},
                {"show": "pair", "narration": "The two electrons form a shared pair of electrons that sits between the two nuclei."},
                {"show": "result", "narration": "Now each hydrogen atom counts two electrons in its outer shell. That shared pair is a covalent bond."},
            ],
        },
        {
            "kind": "molecule_examples",
            "heading": "Covalent bonds are everywhere",
            "params": {
                "molecules": [
                    {
                        "formula": "H_2", "name": "Hydrogen gas",
                        "atoms": [{"symbol": "H", "x": -55, "y": 0}, {"symbol": "H", "x": 55, "y": 0}],
                        "bonds": [[0, 1]],
                    },
                    {
                        "formula": "H_2O", "name": "Water",
                        "atoms": [
                            {"symbol": "O", "x": 0, "y": -25},
                            {"symbol": "H", "x": -80, "y": 40},
                            {"symbol": "H", "x": 80, "y": 40},
                        ],
                        "bonds": [[0, 1], [0, 2]],
                    },
                    {
                        "formula": "Cl_2", "name": "Chlorine gas",
                        "atoms": [{"symbol": "Cl", "x": -60, "y": 0}, {"symbol": "Cl", "x": 60, "y": 0}],
                        "bonds": [[0, 1]],
                    },
                ]
            },
            "segments": [
                {"show": "mol1", "narration": "Hydrogen gas is two hydrogen atoms joined by one shared pair."},
                {"show": "mol2", "narration": "In water, oxygen shares one pair with each of two hydrogen atoms."},
                {"show": "mol3", "narration": "And chlorine gas forms when two chlorine atoms share a pair, so both reach eight."},
            ],
        },
        {
            "kind": "bullets",
            "heading": "Key takeaways",
            "params": {
                "items": [
                    "Atoms are most stable with a full outer shell",
                    "Non-metal atoms can share electrons instead of transferring them",
                    "Each shared pair of electrons is one covalent bond",
                ]
            },
            "segments": [
                {"show": "item1", "narration": "To recap: atoms are most stable when their outer shell is full."},
                {"show": "item2", "narration": "Instead of giving electrons away, non-metal atoms can share them."},
                {"show": "item3", "narration": "Each shared pair of electrons is a covalent bond, and it makes both atoms more stable."},
            ],
        },
    ],
}

TOPIC = TopicSpec(
    id="covalent_bonds",
    subject="chemistry",
    title="Why Atoms Form Covalent Bonds",
    canonical_query="Why do atoms form covalent bonds?",
    match_patterns=(frozenset({"covalent"}),),
    required_terms=("outer shell", "share", "pair of electrons", "stable", "covalent bond"),
    reference_plan=REFERENCE_PLAN,
)
