"""DB-backed lookup for the simulated third-party ingredient_server.
Deliberately NOT imported by anything under app/agent/ - this file plays the
part of a vendor's own, separately-maintained data. Its records now live in
the same Postgres instance the rest of this app already runs
(app.database.engine), seeded via seed_ingredients.py, rather than a Python
literal - a genuine external table this "vendor" happens to keep in our DB,
not an in-process dict.
"""

import difflib

from sqlmodel import Session, select

from app.database import engine
from app.mcp_servers.ingredient_db_models import IngredientRecord


def lookup(name: str) -> dict:
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    with Session(engine) as session:
        entry = session.get(IngredientRecord, key)
        if entry is not None:
            return {
                "found": True,
                "matched_name": entry.name,
                "suggestion": None,
                "allergen_tags": entry.allergen_tags.split(","),
                "calories_kcal_per_100g": entry.calories_kcal_per_100g,
                "protein_g": entry.protein_g,
                "carbs_g": entry.carbs_g,
                "fat_g": entry.fat_g,
            }
        all_names = session.exec(select(IngredientRecord.name)).all()

    matches = difflib.get_close_matches(key, all_names, n=1, cutoff=0.6)
    suggestion = matches[0] if matches else None
    return {
        "found": False,
        "matched_name": None,
        "suggestion": suggestion,
        "allergen_tags": [],
        "calories_kcal_per_100g": None,
        "protein_g": None,
        "carbs_g": None,
        "fat_g": None,
    }
