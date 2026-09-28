"""Table definition for the simulated third-party ingredient database.
Lives in the same Postgres instance the rest of this app already uses
(app.database.engine) - the vendor's data is now a real DB table seeded by
seed_ingredients.py, not a Python literal."""

from sqlmodel import Field, SQLModel


class IngredientRecord(SQLModel, table=True):
    name: str = Field(primary_key=True)
    allergen_tags: str  # comma-separated, e.g. "dairy" or "none"
    calories_kcal_per_100g: float
    protein_g: float
    carbs_g: float
    fat_g: float
