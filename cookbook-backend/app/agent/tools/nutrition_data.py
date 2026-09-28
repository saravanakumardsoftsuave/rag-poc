"""Static per-100g nutrition + allergen table for ingredients that actually
appear in the two ingested cookbooks. No live nutrition API is available
offline, so this is a small deterministic stand-in, not a real database."""

import difflib
from typing import Literal, TypedDict

Allergen = Literal["dairy", "gluten", "tree_nut", "peanut", "soy", "egg", "shellfish", "none"]


class NutritionEntry(TypedDict):
    calories_kcal_per_100g: float
    protein_g: float
    carbs_g: float
    fat_g: float
    allergen_tags: list[Allergen]


NUTRITION_TABLE: dict[str, NutritionEntry] = {
    "paneer": {"calories_kcal_per_100g": 265, "protein_g": 18, "carbs_g": 3, "fat_g": 21, "allergen_tags": ["dairy"]},
    "khoya": {"calories_kcal_per_100g": 421, "protein_g": 15, "carbs_g": 27, "fat_g": 29, "allergen_tags": ["dairy"]},
    "milk": {"calories_kcal_per_100g": 61, "protein_g": 3.2, "carbs_g": 4.8, "fat_g": 3.3, "allergen_tags": ["dairy"]},
    "cream": {"calories_kcal_per_100g": 340, "protein_g": 2.1, "carbs_g": 2.8, "fat_g": 36, "allergen_tags": ["dairy"]},
    "butter": {"calories_kcal_per_100g": 717, "protein_g": 0.9, "carbs_g": 0.1, "fat_g": 81, "allergen_tags": ["dairy"]},
    "ghee": {"calories_kcal_per_100g": 900, "protein_g": 0, "carbs_g": 0, "fat_g": 100, "allergen_tags": ["dairy"]},
    "curd": {"calories_kcal_per_100g": 61, "protein_g": 3.5, "carbs_g": 4.7, "fat_g": 3.3, "allergen_tags": ["dairy"]},
    "yogurt": {"calories_kcal_per_100g": 61, "protein_g": 3.5, "carbs_g": 4.7, "fat_g": 3.3, "allergen_tags": ["dairy"]},
    "all_purpose_flour": {"calories_kcal_per_100g": 364, "protein_g": 10, "carbs_g": 76, "fat_g": 1, "allergen_tags": ["gluten"]},
    "wheat_atta": {"calories_kcal_per_100g": 340, "protein_g": 12, "carbs_g": 72, "fat_g": 2, "allergen_tags": ["gluten"]},
    "cashews": {"calories_kcal_per_100g": 553, "protein_g": 18, "carbs_g": 30, "fat_g": 44, "allergen_tags": ["tree_nut"]},
    "almonds": {"calories_kcal_per_100g": 579, "protein_g": 21, "carbs_g": 22, "fat_g": 50, "allergen_tags": ["tree_nut"]},
    "peanuts": {"calories_kcal_per_100g": 567, "protein_g": 26, "carbs_g": 16, "fat_g": 49, "allergen_tags": ["peanut"]},
    "soy_chunks": {"calories_kcal_per_100g": 345, "protein_g": 52, "carbs_g": 33, "fat_g": 0.5, "allergen_tags": ["soy"]},
    "tofu": {"calories_kcal_per_100g": 76, "protein_g": 8, "carbs_g": 1.9, "fat_g": 4.8, "allergen_tags": ["soy"]},
    "soy_milk": {"calories_kcal_per_100g": 54, "protein_g": 3.3, "carbs_g": 6, "fat_g": 1.8, "allergen_tags": ["soy"]},
    "egg": {"calories_kcal_per_100g": 155, "protein_g": 13, "carbs_g": 1.1, "fat_g": 11, "allergen_tags": ["egg"]},
    "coconut": {"calories_kcal_per_100g": 354, "protein_g": 3.3, "carbs_g": 15, "fat_g": 33, "allergen_tags": ["tree_nut"]},
    "shrimp": {"calories_kcal_per_100g": 99, "protein_g": 24, "carbs_g": 0.2, "fat_g": 0.3, "allergen_tags": ["shellfish"]},
    "toor_dal": {"calories_kcal_per_100g": 343, "protein_g": 22, "carbs_g": 58, "fat_g": 1.5, "allergen_tags": ["none"]},
    "urad_dal": {"calories_kcal_per_100g": 341, "protein_g": 25, "carbs_g": 59, "fat_g": 1.6, "allergen_tags": ["none"]},
    "rice": {"calories_kcal_per_100g": 130, "protein_g": 2.7, "carbs_g": 28, "fat_g": 0.3, "allergen_tags": ["none"]},
    "chickpea_flour_besan": {"calories_kcal_per_100g": 387, "protein_g": 22, "carbs_g": 58, "fat_g": 6.7, "allergen_tags": ["none"]},
    "sunflower_seeds": {"calories_kcal_per_100g": 584, "protein_g": 21, "carbs_g": 20, "fat_g": 51, "allergen_tags": ["none"]},
    "oat_milk": {"calories_kcal_per_100g": 47, "protein_g": 1, "carbs_g": 7.5, "fat_g": 1.5, "allergen_tags": ["none"]},
    "oat_cream": {"calories_kcal_per_100g": 200, "protein_g": 1.5, "carbs_g": 12, "fat_g": 16, "allergen_tags": ["none"]},
    "coconut_oil": {"calories_kcal_per_100g": 862, "protein_g": 0, "carbs_g": 0, "fat_g": 100, "allergen_tags": ["tree_nut"]},
    "sunflower_oil": {"calories_kcal_per_100g": 884, "protein_g": 0, "carbs_g": 0, "fat_g": 100, "allergen_tags": ["none"]},
    "tamarind": {"calories_kcal_per_100g": 239, "protein_g": 2.8, "carbs_g": 63, "fat_g": 0.6, "allergen_tags": ["none"]},
}


def resolve_ingredient_key(name: str) -> str | None:
    normalized = _normalize(name)
    if normalized in NUTRITION_TABLE:
        return normalized
    # Recipe text is phrased loosely ("fresh cream", "whole black urad dal"),
    # so fall back to substring containment against the table's canonical
    # keys (longest first, to prefer the more specific match).
    for key in sorted(NUTRITION_TABLE.keys(), key=len, reverse=True):
        if key in normalized or normalized in key:
            return key
    return None


def get_ingredient(name: str) -> NutritionEntry | None:
    key = resolve_ingredient_key(name)
    return NUTRITION_TABLE[key] if key else None


def find_similar(name: str, n: int = 1) -> list[str]:
    return difflib.get_close_matches(_normalize(name), NUTRITION_TABLE.keys(), n=n, cutoff=0.6)


def _normalize(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")
