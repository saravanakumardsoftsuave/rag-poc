"""Raw seed values for the simulated third-party ingredient database.
Used only by seed_ingredients.py - kept separate from ingredient_db_data.py
so the lookup path only ever talks to Postgres, never this literal."""

SEED_DATA: dict[str, dict] = {
    "paneer": {"allergen_tags": "dairy", "calories_kcal_per_100g": 265, "protein_g": 18, "carbs_g": 3, "fat_g": 21},
    "khoya": {"allergen_tags": "dairy", "calories_kcal_per_100g": 421, "protein_g": 15, "carbs_g": 27, "fat_g": 29},
    "milk": {"allergen_tags": "dairy", "calories_kcal_per_100g": 61, "protein_g": 3.2, "carbs_g": 4.8, "fat_g": 3.3},
    "cream": {"allergen_tags": "dairy", "calories_kcal_per_100g": 340, "protein_g": 2.1, "carbs_g": 2.8, "fat_g": 36},
    "butter": {"allergen_tags": "dairy", "calories_kcal_per_100g": 717, "protein_g": 0.9, "carbs_g": 0.1, "fat_g": 81},
    "cashews": {"allergen_tags": "tree_nut", "calories_kcal_per_100g": 553, "protein_g": 18, "carbs_g": 30, "fat_g": 44},
    "coconut": {"allergen_tags": "tree_nut", "calories_kcal_per_100g": 354, "protein_g": 3.3, "carbs_g": 15, "fat_g": 33},
    "peanuts": {"allergen_tags": "peanut", "calories_kcal_per_100g": 567, "protein_g": 26, "carbs_g": 16, "fat_g": 49},
    "tofu": {"allergen_tags": "soy", "calories_kcal_per_100g": 76, "protein_g": 8, "carbs_g": 1.9, "fat_g": 4.8},
    "egg": {"allergen_tags": "egg", "calories_kcal_per_100g": 155, "protein_g": 13, "carbs_g": 1.1, "fat_g": 11},
    "shrimp": {"allergen_tags": "shellfish", "calories_kcal_per_100g": 99, "protein_g": 24, "carbs_g": 0.2, "fat_g": 0.3},
    "toor_dal": {"allergen_tags": "none", "calories_kcal_per_100g": 343, "protein_g": 22, "carbs_g": 58, "fat_g": 1.5},
    "rice": {"allergen_tags": "none", "calories_kcal_per_100g": 130, "protein_g": 2.7, "carbs_g": 28, "fat_g": 0.3},
    # covered by the vendor's DB but NOT by our own static table - a genuine
    # before/after difference when this server is added.
    "paprika": {"allergen_tags": "none", "calories_kcal_per_100g": 282, "protein_g": 14, "carbs_g": 54, "fat_g": 13},
    "ginger": {"allergen_tags": "none", "calories_kcal_per_100g": 80, "protein_g": 1.8, "carbs_g": 18, "fat_g": 0.8},
}
