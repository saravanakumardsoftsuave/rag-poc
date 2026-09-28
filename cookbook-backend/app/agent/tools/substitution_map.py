"""Static, ranked ingredient -> substitute table.

Deliberately seeded with first-choice collisions (a top candidate that is
itself tagged with the same allergen family) so that some race requests
genuinely need a second substitution pass once the first substitute is
checked against the full exclude list - e.g. cashews' top candidate is
almonds (still tree_nut) before falling through to sunflower_seeds (none).
"""

from app.agent.tools.nutrition_data import Allergen

SubstituteCandidate = dict  # {"name": str, "allergen_tags": list[Allergen]}

SUBSTITUTION_MAP: dict[str, list[SubstituteCandidate]] = {
    "paneer": [
        {"name": "tofu", "allergen_tags": ["soy"]},
        {"name": "sunflower_seeds", "allergen_tags": ["none"]},
    ],
    "cream": [
        {"name": "cashews", "allergen_tags": ["tree_nut"]},  # ground into "cashew cream"
        {"name": "coconut", "allergen_tags": ["tree_nut"]},  # ground into "coconut cream"
        {"name": "oat_cream", "allergen_tags": ["none"]},
    ],
    "butter": [
        {"name": "ghee", "allergen_tags": ["dairy"]},
        {"name": "coconut_oil", "allergen_tags": ["tree_nut"]},
        {"name": "sunflower_oil", "allergen_tags": ["none"]},
    ],
    "milk": [
        {"name": "soy_milk", "allergen_tags": ["soy"]},
        {"name": "oat_milk", "allergen_tags": ["none"]},
    ],
    "khoya": [
        {"name": "cashews", "allergen_tags": ["tree_nut"]},  # ground into a mawa-style paste
        {"name": "coconut", "allergen_tags": ["tree_nut"]},
        {"name": "oat_milk", "allergen_tags": ["none"]},  # reduced with sugar into a mawa substitute
    ],
    "ghee": [
        {"name": "butter", "allergen_tags": ["dairy"]},
        {"name": "coconut_oil", "allergen_tags": ["tree_nut"]},
        {"name": "sunflower_oil", "allergen_tags": ["none"]},
    ],
    "all_purpose_flour": [
        {"name": "chickpea_flour_besan", "allergen_tags": ["none"]},
    ],
    "wheat_atta": [
        {"name": "chickpea_flour_besan", "allergen_tags": ["none"]},
    ],
    "cashews": [
        {"name": "almonds", "allergen_tags": ["tree_nut"]},
        {"name": "sunflower_seeds", "allergen_tags": ["none"]},
    ],
    "coconut": [
        {"name": "cashews", "allergen_tags": ["tree_nut"]},  # ground into "cashew cream"
        {"name": "sunflower_seeds", "allergen_tags": ["none"]},  # ground into "sunflower seed cream"
    ],
    "curd": [
        {"name": "soy_milk", "allergen_tags": ["soy"]},
        {"name": "oat_milk", "allergen_tags": ["none"]},
    ],
    "yogurt": [
        {"name": "soy_milk", "allergen_tags": ["soy"]},
        {"name": "oat_milk", "allergen_tags": ["none"]},
    ],
    # Second-tier chains: reached only when a first-round substitute (above)
    # itself conflicts with the requester's full exclude list and needs its
    # own substitute in turn (the cascading case).
    "coconut_oil": [
        {"name": "sunflower_oil", "allergen_tags": ["none"]},
    ],
    "almonds": [
        {"name": "sunflower_seeds", "allergen_tags": ["none"]},
    ],
    "tofu": [
        {"name": "sunflower_seeds", "allergen_tags": ["none"]},
    ],
    "soy_milk": [
        {"name": "oat_milk", "allergen_tags": ["none"]},
    ],
}


def get_candidates(ingredient: str) -> list[SubstituteCandidate]:
    normalized = _normalize(ingredient)
    if normalized in SUBSTITUTION_MAP:
        return SUBSTITUTION_MAP[normalized]
    for key in sorted(SUBSTITUTION_MAP.keys(), key=len, reverse=True):
        if key in normalized or normalized in key:
            return SUBSTITUTION_MAP[key]
    return []


def candidate_conflicts(candidate: SubstituteCandidate, exclude_allergens: list[Allergen], diet: str) -> bool:
    tags = set(candidate["allergen_tags"])
    if tags & set(exclude_allergens):
        return True
    if diet == "vegan" and ({"dairy", "egg"} & tags):
        return True
    if diet == "vegetarian" and ({"shellfish"} & tags) and candidate["name"] in ("shrimp",):
        return True
    return False


def _normalize(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")
