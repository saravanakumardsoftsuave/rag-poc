"""Seeds (or updates) the ingredient_record table in the shared Postgres DB.

Run with: python -m app.mcp_servers.seed_ingredients
"""

from sqlmodel import Session, SQLModel

from app.database import engine
from app.mcp_servers.ingredient_db_models import IngredientRecord
from app.mcp_servers.ingredient_seed_data import SEED_DATA


def seed() -> int:
    SQLModel.metadata.create_all(engine, tables=[IngredientRecord.__table__])
    with Session(engine) as session:
        for name, values in SEED_DATA.items():
            existing = session.get(IngredientRecord, name)
            if existing is not None:
                for key, value in values.items():
                    setattr(existing, key, value)
            else:
                session.add(IngredientRecord(name=name, **values))
        session.commit()
    return len(SEED_DATA)


if __name__ == "__main__":
    count = seed()
    print(f"Seeded {count} ingredients into Postgres (ingredient_record table).")
