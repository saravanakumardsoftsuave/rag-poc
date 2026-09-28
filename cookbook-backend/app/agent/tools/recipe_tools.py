"""The three recipe-adaptation tools (W7): search_recipes, get_nutrition,
substitute_ingredient. Plain functions - the single source of truth reused by
the MCP server, the fixed workflow, and the race harness."""

import json
import logging
import re
from typing import Literal

from app.agent.tools.nutrition_data import find_similar, get_ingredient, resolve_ingredient_key
from app.agent.tools.substitution_map import get_candidates
from app.database import has_ingested_documents
from app.prompt import build_recipe_extraction_prompt
from app.rag import NO_RELEVANT_ANSWER, generate_answer
from app.retrieval import hybrid_search

logger = logging.getLogger(__name__)

Allergen = Literal["dairy", "gluten", "tree_nut", "peanut", "soy", "egg", "shellfish", "none"]
Diet = Literal["vegan", "vegetarian", "none"]

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def search_recipes(query: str, cuisine: Literal["north_indian", "south_indian", "any"] = "any") -> dict:
    """Finds a single named recipe already ingested in the cookbooks and
    returns its base servings, ingredient list with quantities, and method
    steps. Does not compute nutrition and does not suggest substitutes."""
    if not has_ingested_documents():
        return {"found": False, "message": NO_RELEVANT_ANSWER, "recipe_name": None, "servings": None,
                "ingredients": [], "method": [], "sources": []}

    matches, best_score = hybrid_search(query, k=5)
    if cuisine != "any":
        filename_hint = "north" if cuisine == "north_indian" else "south"
        filtered = [m for m in matches if filename_hint in m["source"].lower()]
        matches = filtered or matches
    if not matches:
        return {"found": False, "message": NO_RELEVANT_ANSWER, "recipe_name": None, "servings": None,
                "ingredients": [], "method": [], "sources": []}

    context = "\n\n".join(m["text"] for m in matches[:3])
    raw = generate_answer(build_recipe_extraction_prompt(query, context))
    parsed = _extract_json(raw)
    if parsed is None:
        logger.warning("search_recipes: could not parse extraction JSON for query=%r raw=%r", query, raw)
        return {"found": False, "message": "Could not extract a structured recipe from the cookbook text.",
                "recipe_name": None, "servings": None, "ingredients": [], "method": [], "sources": []}

    sources = sorted({m["source"] for m in matches})
    return {
        "found": True,
        "recipe_name": parsed.get("recipe_name"),
        "servings": parsed.get("servings"),
        "ingredients": parsed.get("ingredients", []),
        "method": parsed.get("method", []),
        "sources": sources,
    }


def get_nutrition(ingredient: str) -> dict:
    """Looks up per-100g calories, macros, and allergen tags for one named
    ingredient already in the nutrition table. Does not search recipes and
    does not propose a substitute - call substitute_ingredient for that."""
    entry = get_ingredient(ingredient)
    if entry is not None:
        return {"ingredient": ingredient, "found": True, "matched_name": resolve_ingredient_key(ingredient), **entry,
                "suggestion": None, "message": None}

    suggestions = find_similar(ingredient)
    suggestion = suggestions[0] if suggestions else None
    message = (
        f"no ingredient matched '{ingredient}': try '{suggestion}'"
        if suggestion
        else f"no ingredient matched '{ingredient}' and no close match was found"
    )
    return {
        "ingredient": ingredient, "found": False, "matched_name": None,
        "calories_kcal_per_100g": None, "protein_g": None, "carbs_g": None, "fat_g": None,
        "allergen_tags": [], "suggestion": suggestion, "message": message,
    }


def substitute_ingredient(ingredient: str, exclude_allergens: list[Allergen], diet: Diet = "none") -> dict:
    """Given one ingredient and the allergens/diet to avoid, returns a single
    safe substitute with its own allergen tags. Does not look up nutrition
    values and does not search recipes."""
    candidates = get_candidates(ingredient)
    if not candidates:
        return {"original": ingredient, "found": False, "substitute": None, "substitute_allergen_tags": [],
                "candidates_rejected": [], "rationale": f"No known substitute for '{ingredient}'."}

    exclude_set = set(exclude_allergens)
    rejected = []
    for candidate in candidates:
        tags = set(candidate["allergen_tags"])
        violates_diet = diet == "vegan" and bool({"dairy", "egg"} & tags)
        if tags & exclude_set or violates_diet:
            rejected.append(candidate["name"])
            continue
        return {
            "original": ingredient,
            "found": True,
            "substitute": candidate["name"],
            "substitute_allergen_tags": candidate["allergen_tags"],
            "candidates_rejected": rejected,
            "rationale": f"'{candidate['name']}' avoids {sorted(exclude_set) or 'no'} allergens"
            + (f" and fits a {diet} diet" if diet != "none" else "") + ".",
        }

    return {
        "original": ingredient,
        "found": False,
        "substitute": None,
        "substitute_allergen_tags": [],
        "candidates_rejected": rejected,
        "rationale": f"Every known candidate for '{ingredient}' conflicts with {sorted(exclude_set)}.",
    }


_FRACTION_IN_NUMBER = re.compile(r'(?<=[\s:\[,-])(\d+)\s*/\s*(\d+)(?=[\s,\]}])')


def _extract_json(text: str) -> dict | None:
    text = text.replace("```json", "```").split("```")[1] if "```" in text else text
    match = _JSON_BLOCK.search(text)
    if not match:
        return None
    candidate = match.group()
    # The model sometimes writes a bare fraction ("1/4") as a JSON number,
    # which is invalid JSON - coerce it to a decimal before parsing rather
    # than failing the whole extraction over one malformed field.
    candidate = _FRACTION_IN_NUMBER.sub(lambda m: str(int(m.group(1)) / int(m.group(2))), candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
