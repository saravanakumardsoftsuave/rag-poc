"""Fixed workflow twin of the recipe-adaptation agent (W7 requirement 2):
hard-coded steps, the SAME tool implementations, the SAME model for the final
phrasing, the SAME output contract - no LLM decides what happens next. Used
only by the eval race (evals/race.py), not by the live app.
"""

from app.agent.tools.recipe_tools import get_nutrition, search_recipes, substitute_ingredient
from app.prompt import build_general_prompt
from app.rag import generate_answer


def run_fixed_workflow(recipe_query: str, requested_servings: int, exclude_allergens: list[str],
                        diet: str = "none") -> dict:
    recipe = search_recipes(recipe_query)
    if not recipe.get("found"):
        return {
            "recipe_name": None, "requested_servings": requested_servings, "scaled_ingredients": [],
            "method": [], "substitutions_made": [], "warnings": [recipe.get("message", "Recipe not found.")],
            "sources": [],
        }

    base_servings = recipe.get("servings") or requested_servings
    ratio = requested_servings / base_servings if base_servings else 1.0

    scaled_ingredients = []
    substitutions_made = []
    warnings = []

    for ingredient in recipe.get("ingredients", []):
        name = ingredient.get("name", "")
        unit = ingredient.get("unit", "")
        try:
            scaled_quantity = round(float(ingredient.get("quantity", 0)) * ratio, 3)
        except (TypeError, ValueError):
            # non-numeric quantities ("a pinch", "to taste") are carried through unscaled
            scaled_quantity = ingredient.get("quantity", "")

        nutrition = get_nutrition(name)
        conflicting_tags = [t for t in nutrition.get("allergen_tags", []) if t in exclude_allergens]
        final_name = name

        if conflicting_tags:
            # First pass: substitute against only the tag(s) this specific
            # ingredient itself triggered.
            sub = substitute_ingredient(name, exclude_allergens=conflicting_tags, diet=diet)
            passes = 1
            current = sub
            # Bounded (compile-time, not LLM-decided) retry: if the accepted
            # substitute itself still conflicts with the FULL exclude list,
            # substitute it again. This is the cascading case from the spec.
            while (
                passes < 2
                and current.get("found")
                and set(current.get("substitute_allergen_tags", [])) & set(exclude_allergens)
            ):
                current = substitute_ingredient(current["substitute"], exclude_allergens=exclude_allergens, diet=diet)
                passes += 1

            if current.get("found"):
                final_name = current["substitute"]
                substitutions_made.append({
                    "from": name, "to": final_name, "reason": f"avoids {conflicting_tags}",
                    "passes": passes,
                })
            else:
                warnings.append(f"Could not find a safe substitute for '{name}'.")

        scaled_ingredients.append({
            "name": final_name, "quantity": scaled_quantity, "unit": unit,
            "substituted_from": name if final_name != name else None,
        })

    return {
        "recipe_name": recipe.get("recipe_name"),
        "requested_servings": requested_servings,
        "scaled_ingredients": scaled_ingredients,
        "method": recipe.get("method", []),
        "substitutions_made": substitutions_made,
        "warnings": warnings,
        "sources": recipe.get("sources", []),
    }


def phrase_workflow_result(result: dict) -> str:
    """One fixed generate_answer call to phrase the assembled result as
    prose - same model, same call shape the agent uses for its FINAL answer."""
    summary_lines = [
        f"Recipe: {result['recipe_name']}",
        f"Servings requested: {result['requested_servings']}",
        "Ingredients: " + "; ".join(
            f"{i['quantity']} {i['unit']} {i['name']}" + (f" (was {i['substituted_from']})" if i["substituted_from"] else "")
            for i in result["scaled_ingredients"]
        ),
        "Method: " + " ".join(result["method"]),
    ]
    if result["warnings"]:
        summary_lines.append("Warnings: " + "; ".join(result["warnings"]))
    prompt = build_general_prompt(
        "Phrase this adapted recipe naturally for the user:\n" + "\n".join(summary_lines)
    )
    return generate_answer(prompt)
