"""W10: multi-agent orchestrator. Decomposes a recipe-adaptation request,
delegates sequentially to a narrow substitution worker (search_recipes +
substitute_ingredient only) and a narrow allergen/nutrition worker
(get_nutrition + lookup_ingredient only - deliberately FEWER tools than the
single W7 agent has, since that narrowing is the only plausible source of a
real win per W10-Task-Set-B.md's own warning), then synthesizes one final
answer. Every hand-off's token count is logged to evals/handoffs.log so the
context re-send multiplier this week's assignment wants can be computed and
attributed to a real, named hand-off rather than guessed at.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from app.agent.core.budgets import Budgets, NOMINAL_USD_PER_1K_TOKENS
from app.agent.core.loop import run_agentic_loop
from app.agent.core.registry import local_registry
from app.agent.tools.recipe_tools import get_nutrition, search_recipes, substitute_ingredient
from app.mcp_servers.ingredient_db_data import lookup as _lookup_ingredient_row
from app.rag import generate_answer, get_generator
from evals.checker import check_result

logger = logging.getLogger(__name__)

# Narrower than race.py's RACE_BUDGETS (single agent) - fewer tools per
# worker should need fewer turns to finish its narrower job.
WORKER_BUDGETS = Budgets(max_iterations=3, max_tokens=2500, max_cost_usd=0.05, timeout_s=180.0)

HANDOFF_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "evals" / "handoffs.log"

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

SUB_TOOL_HINT = (
    "Use search_recipes to find the recipe and its ingredients, then use "
    "substitute_ingredient (args: ingredient, exclude_allergens, diet) for any "
    "ingredient whose allergen tags conflict with the avoid-list - call it again "
    "on the returned substitute if THAT substitute's own tags still conflict."
)
ALLERGEN_TOOL_HINT = (
    "Use get_nutrition (args: ingredient) and lookup_ingredient (args: name) to "
    "confirm nutrition and allergen information for the ingredients listed below."
)


def lookup_ingredient(name: str) -> dict:
    """Looks up allergen tags and per-100g nutrition for one ingredient from
    the (Postgres-backed) ingredient database."""
    return _lookup_ingredient_row(name)


def _count_tokens(text: str) -> int:
    return len(get_generator().tokenizer(text)["input_ids"])


def _log_handoff(line: str) -> None:
    HANDOFF_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HANDOFF_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _extract_json(text: str) -> dict | None:
    body = text.replace("```json", "```").split("```")[1] if "```" in text else text
    match = _JSON_BLOCK.search(body)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _build_decompose_prompt(request) -> str:
    return (
        "You are an orchestrator for a recipe-adaptation assistant. Restate the "
        "request below as two short task briefs: one for a substitution worker "
        "(who only searches recipes and substitutes ingredients) and one for an "
        "allergen/nutrition worker (who only looks up nutrition and allergen "
        "data). Reply with exactly this JSON shape, no other text:\n"
        '{"substitution_brief": "...", "allergen_brief": "..."}\n\n'
        f"Recipe: {request.recipe_query}\n"
        f"Requested servings: {request.requested_servings}\n"
        f"Allergens to avoid: {request.exclude_allergens or 'none'}\n"
        f"Diet: {request.diet}"
    )


def _decompose(request) -> tuple[dict[str, str], int]:
    prompt = _build_decompose_prompt(request)
    raw = generate_answer(prompt)
    tokens = _count_tokens(prompt) + _count_tokens(raw)
    parsed = _extract_json(raw)
    if not parsed or "substitution_brief" not in parsed or "allergen_brief" not in parsed:
        logger.warning("orchestrator: decomposition parse failed, using template fallback. raw=%r", raw)
        parsed = {
            "substitution_brief": (
                f"Adapt '{request.recipe_query}' to serve {request.requested_servings}. "
                f"Avoid allergens: {request.exclude_allergens or 'none'}. Diet: {request.diet}."
            ),
            "allergen_brief": (
                f"Confirm nutrition and allergen safety for '{request.recipe_query}', "
                f"avoiding: {request.exclude_allergens or 'none'}. Diet: {request.diet}."
            ),
        }
    return parsed, tokens


def _build_worker_prompt(brief: str, tool_hint: str) -> str:
    return (
        f"{brief}\n\n{tool_hint}\n\n"
        'Once you have the information you need, reply FINAL with {"answer": "done", "sources": []}.'
    )


def _build_synthesis_prompt(request, adapted: dict, allergen_tool_calls: list[dict], allergen_failed: bool) -> str:
    if allergen_failed:
        allergen_summary = (
            "ALLERGEN/NUTRITION CHECK FAILED - no confirmed allergen-safety data is "
            "available for this batch of ingredients. Do not claim the dish is safe "
            "for any excluded allergen - state plainly that this could not be verified."
        )
    else:
        allergen_summary = json.dumps([c["result"] for c in allergen_tool_calls])
    return (
        "You are finishing a recipe-adaptation request. Write one short, friendly "
        "final answer for the user summarizing the adapted recipe below. Be "
        "accurate - only state an allergen is avoided if the allergen/nutrition "
        "data below actually confirms it.\n\n"
        f"Adapted recipe (JSON): {json.dumps(adapted)}\n\n"
        f"Allergen/nutrition data: {allergen_summary}\n\n"
        f"Requested: avoid {request.exclude_allergens or 'none'}, diet {request.diet}.\n\n"
        "Answer:"
    )


async def run_orchestrator_request(request, inject_failure: bool = False) -> dict[str, Any]:
    from evals.race import _reconstruct_from_tool_calls  # reused, not duplicated

    start = time.perf_counter()
    total_tokens = 0
    warnings: list[str] = []

    decompose_parsed, decompose_tokens = _decompose(request)
    total_tokens += decompose_tokens
    _log_handoff(f"{request.id} | orchestrator->decompose | tokens_total={decompose_tokens}")

    # --- substitution worker ---
    sub_registry = local_registry(search_recipes, substitute_ingredient)
    sub_prompt = _build_worker_prompt(decompose_parsed["substitution_brief"], SUB_TOOL_HINT)
    sub_result = await run_agentic_loop(
        sub_prompt, sub_registry, WORKER_BUDGETS, request_id=f"{request.id}:sub"
    )
    sub_tokens = sub_result.get("tokens_used", 0)
    total_tokens += sub_tokens
    _log_handoff(
        f"{request.id} | orchestrator->substitution_worker | tokens_total={sub_tokens} "
        f"iterations={sub_result.get('iterations_used')} status={sub_result.get('status')}"
    )

    adapted = _reconstruct_from_tool_calls(request, sub_result.get("tool_calls", []))

    # --- allergen/nutrition worker (informed by what substitution actually
    # produced - this ingredient-list resend is the named context re-send) ---
    final_ingredient_names = [i["name"] for i in adapted.get("scaled_ingredients", [])]
    allergen_brief = (
        decompose_parsed["allergen_brief"]
        + f"\n\nIngredients to check: {', '.join(final_ingredient_names) or '(none found)'}"
    )
    allergen_prompt = _build_worker_prompt(allergen_brief, ALLERGEN_TOOL_HINT)
    allergen_registry = local_registry(get_nutrition, lookup_ingredient)

    if inject_failure:
        def _failing_get_nutrition(ingredient: str) -> dict:
            raise RuntimeError("simulated 500: allergen service unavailable")

        def _failing_lookup_ingredient(name: str) -> dict:
            raise RuntimeError("simulated 500: allergen service unavailable")

        _failing_get_nutrition.__doc__ = get_nutrition.__doc__
        _failing_lookup_ingredient.__doc__ = lookup_ingredient.__doc__
        allergen_registry = local_registry(_failing_get_nutrition, _failing_lookup_ingredient)

    allergen_failed = False
    allergen_tool_calls: list[dict] = []
    try:
        allergen_result = await run_agentic_loop(
            allergen_prompt, allergen_registry, WORKER_BUDGETS, request_id=f"{request.id}:allergen"
        )
        allergen_tokens = allergen_result.get("tokens_used", 0)
        total_tokens += allergen_tokens
        allergen_tool_calls = allergen_result.get("tool_calls", [])
        _log_handoff(
            f"{request.id} | orchestrator->allergen_worker | tokens_total={allergen_tokens} "
            f"iterations={allergen_result.get('iterations_used')} status={allergen_result.get('status')}"
        )
    except Exception as exc:  # noqa: BLE001 - deliberately broad: run_agentic_loop
        # does not itself catch generic tool exceptions (only TypeError, for
        # bad args), so a tool raising RuntimeError propagates all the way out
        # here uncaught - this IS the orchestrator's only line of defense, and
        # exactly what W10 requirement 4 asks to be observed and recorded.
        allergen_failed = True
        warnings.append(f"allergen/nutrition check unavailable: {exc}")
        _log_handoff(
            f"{request.id} | orchestrator->allergen_worker | FAILED: {exc} "
            "(tokens_total=unknown - run_agentic_loop raised before returning its "
            "tracker state, so partial spend on this turn is not recoverable)"
        )

    if warnings:
        adapted["warnings"] = list(adapted.get("warnings", [])) + warnings

    # --- synthesis ---
    synthesis_prompt = _build_synthesis_prompt(request, adapted, allergen_tool_calls, allergen_failed)
    final_answer_text = generate_answer(synthesis_prompt)
    synthesis_tokens = _count_tokens(synthesis_prompt) + _count_tokens(final_answer_text)
    total_tokens += synthesis_tokens
    _log_handoff(f"{request.id} | orchestrator->synthesis | tokens_total={synthesis_tokens}")

    passed, problems = check_result(request, adapted)
    latency_ms = (time.perf_counter() - start) * 1000
    cost_usd = total_tokens * NOMINAL_USD_PER_1K_TOKENS / 1000

    return {
        "system": "orchestrator",
        "request_id": request.id,
        "passed": passed,
        "latency_ms": round(latency_ms, 1),
        "tokens_total": total_tokens,
        "cost_usd": round(cost_usd, 5),
        "problems": problems,
        "final_answer_text": final_answer_text,
        "allergen_failed": allergen_failed,
    }
