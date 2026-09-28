"""Deterministic pass/fail correctness checker for one race request's result
(the AdaptationResult-shaped dict both the agent and the fixed workflow
produce). Used by race.py so pass/fail isn't a judgment call.
"""

from evals.requests import RaceRequest

TOLERANCE = 0.05


def check_result(request: RaceRequest, result: dict) -> tuple[bool, list[str]]:
    problems: list[str] = []

    if not result.get("recipe_name"):
        return False, ["no recipe_name in result"]
    if not result.get("scaled_ingredients"):
        problems.append("no scaled_ingredients in result")
    if not result.get("method"):
        problems.append("no method steps in result")

    original_names = {
        i.get("substituted_from") or i.get("name")
        for i in result.get("scaled_ingredients", [])
    }
    # every substitute's own allergen tags (if we can look them up) must be
    # disjoint from what the request excluded
    from app.agent.tools.nutrition_data import get_ingredient

    substitutions = result.get("substitutions_made", [])
    for sub in substitutions:
        entry = get_ingredient(sub["to"])
        if entry and set(entry["allergen_tags"]) & set(request.exclude_allergens):
            problems.append(f"substitute '{sub['to']}' still conflicts with {request.exclude_allergens}")

    if request.cascading:
        cascaded = [s for s in substitutions if s.get("passes", 1) >= 2]
        if not cascaded:
            problems.append("cascade not resolved: no substitution shows 2 passes")

    if request.exclude_allergens == ["dairy", "peanut"] and any(
        "peanut" in str(s.get("reason", "")) for s in substitutions
    ):
        problems.append("invented a peanut substitution where no peanut ingredient existed")

    return (len(problems) == 0), problems
