"""W7 requirement 3: race the agent vs. the fixed workflow over the same 10
recipe-adaptation requests and report 4 numbers per system: pass rate, p50
latency, total tokens, cost/request.

Both systems use the SAME three tools (search_recipes, get_nutrition,
substitute_ingredient) via a LOCAL registry (no MCP) - the race is about the
agent-vs-workflow question, not about MCP, so it skips the subprocess
overhead a real MCP round trip would add per call.
"""

import asyncio
import csv
import json
import logging
import statistics
import time
from pathlib import Path

from app.agent.core.budgets import Budgets, NOMINAL_USD_PER_1K_TOKENS
from app.agent.core.loop import run_agentic_loop
from app.agent.core.registry import local_registry
from app.agent.tools.recipe_tools import get_nutrition, search_recipes, substitute_ingredient
from app.agent.workflow import run_fixed_workflow
from app.rag import get_generator
from evals.checker import check_result
from evals.requests import REQUESTS

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("race")

RACE_BUDGETS = Budgets(max_iterations=5, max_tokens=4000, max_cost_usd=0.05, timeout_s=240.0)


def _count_tokens(text: str) -> int:
    return len(get_generator().tokenizer(text)["input_ids"])


def build_agent_task(request) -> str:
    return (
        f"Adapt the recipe '{request.recipe_query}' to serve {request.requested_servings} people. "
        f"Avoid these allergens: {request.exclude_allergens or 'none'}. Diet: {request.diet}. "
        "Use search_recipes to find the recipe and its ingredients, use substitute_ingredient for any "
        "ingredient whose allergen tags conflict with the avoid-list (call it again on the returned "
        "substitute if THAT substitute's own tags still conflict). Once you've checked every ingredient, "
        "reply FINAL with {\"answer\": \"done\", \"sources\": []}."
    )


def _reconstruct_from_tool_calls(request, tool_calls: list[dict]) -> dict:
    """Turns whatever tools the agent actually called into the same
    AdaptationResult shape run_fixed_workflow produces, so both systems can
    be checked with the identical checker. This is deliberately built from
    the tool_calls transcript, not from the model's own prose FINAL answer -
    it measures what the agent DID, not what it claimed."""
    recipe = None
    for call in tool_calls:
        if call["name"] == "search_recipes" and call["result"].get("found"):
            recipe = call["result"]

    if recipe is None:
        return {"recipe_name": None, "requested_servings": request.requested_servings,
                "scaled_ingredients": [], "method": [], "substitutions_made": [],
                "warnings": ["agent never successfully called search_recipes"], "sources": []}

    base_servings = recipe.get("servings") or request.requested_servings
    ratio = request.requested_servings / base_servings if base_servings else 1.0

    # ingredient -> final substitute name, chasing multi-hop chains
    substitute_of: dict[str, str] = {}
    passes_for: dict[str, int] = {}
    reason_for: dict[str, str] = {}
    for call in tool_calls:
        if call["name"] != "substitute_ingredient" or not call["result"].get("found"):
            continue
        original = call["args"].get("ingredient", call["result"].get("original"))
        substitute = call["result"]["substitute"]
        # if `original` was itself already someone's substitute, this is a second pass
        root = original
        hops = 1
        for existing_root, existing_sub in list(substitute_of.items()):
            if existing_sub == original:
                root = existing_root
                hops = passes_for.get(existing_root, 1) + 1
        substitute_of[root] = substitute
        passes_for[root] = hops
        reason_for[root] = call["result"].get("rationale", "")

    scaled_ingredients = []
    substitutions_made = []
    for ingredient in recipe.get("ingredients", []):
        name = ingredient.get("name", "")
        unit = ingredient.get("unit", "")
        try:
            scaled_quantity = round(float(ingredient.get("quantity", 0)) * ratio, 3)
        except (TypeError, ValueError):
            scaled_quantity = ingredient.get("quantity", "")
        final_name = substitute_of.get(name, name)
        if final_name != name:
            substitutions_made.append({
                "from": name, "to": final_name, "reason": reason_for.get(name, ""),
                "passes": passes_for.get(name, 1),
            })
        scaled_ingredients.append({
            "name": final_name, "quantity": scaled_quantity, "unit": unit,
            "substituted_from": name if final_name != name else None,
        })

    return {
        "recipe_name": recipe.get("recipe_name"),
        "requested_servings": request.requested_servings,
        "scaled_ingredients": scaled_ingredients,
        "method": recipe.get("method", []),
        "substitutions_made": substitutions_made,
        "warnings": [],
        "sources": recipe.get("sources", []),
    }


async def run_agent_request(request) -> dict:
    registry = local_registry(search_recipes, get_nutrition, substitute_ingredient)
    start = time.perf_counter()
    loop_result = await run_agentic_loop(build_agent_task(request), registry, RACE_BUDGETS, request_id=request.id)
    latency_ms = (time.perf_counter() - start) * 1000
    tool_calls = loop_result.get("tool_calls", [])
    adapted = _reconstruct_from_tool_calls(request, tool_calls)
    passed, problems = check_result(request, adapted)
    if loop_result["status"] != "ok":
        passed = False
        problems = problems + [f"loop status={loop_result['status']} ({loop_result.get('reason') or loop_result.get('budget')})"]
    return {
        "system": "agent", "request_id": request.id, "passed": passed,
        "latency_ms": round(latency_ms, 1),
        "tokens_total": loop_result["tokens_used"],
        "cost_usd": round(loop_result["cost_usd"], 5),
        "problems": problems,
    }


def run_workflow_request(request) -> dict:
    start = time.perf_counter()
    result = run_fixed_workflow(request.recipe_query, request.requested_servings, request.exclude_allergens, request.diet)
    from app.agent.workflow import phrase_workflow_result
    phrasing_prompt_tokens = 0
    tokens_total = 0
    if result.get("recipe_name"):
        # one fixed generate_answer call for phrasing, same as the agent's FINAL step
        prompt_text = json.dumps(result)
        tokens_total += _count_tokens(prompt_text)
        answer_text = phrase_workflow_result(result)
        tokens_total += _count_tokens(answer_text)
    latency_ms = (time.perf_counter() - start) * 1000
    passed, problems = check_result(request, result)
    cost_usd = tokens_total * NOMINAL_USD_PER_1K_TOKENS / 1000
    return {
        "system": "workflow", "request_id": request.id, "passed": passed,
        "latency_ms": round(latency_ms, 1), "tokens_total": tokens_total,
        "cost_usd": round(cost_usd, 5), "problems": problems,
    }


async def main():
    rows = []
    for request in REQUESTS:
        print(f"[workflow] {request.id} ...", flush=True)
        wf = run_workflow_request(request)
        print(f"  -> passed={wf['passed']} latency_ms={wf['latency_ms']} tokens={wf['tokens_total']} problems={wf['problems']}")
        rows.append(wf)

    for request in REQUESTS:
        print(f"[agent] {request.id} ...", flush=True)
        ag = await run_agent_request(request)
        print(f"  -> passed={ag['passed']} latency_ms={ag['latency_ms']} tokens={ag['tokens_total']} problems={ag['problems']}")
        rows.append(ag)

    out_path = Path(__file__).parent / "race.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["system", "request_id", "passed", "latency_ms", "tokens_total", "cost_usd"])
        for row in rows:
            writer.writerow([row["system"], row["request_id"], row["passed"], row["latency_ms"],
                              row["tokens_total"], row["cost_usd"]])

    print("\n=== SUMMARY ===")
    for system in ("agent", "workflow"):
        system_rows = [r for r in rows if r["system"] == system]
        pass_rate = sum(r["passed"] for r in system_rows) / len(system_rows)
        p50_latency = statistics.median(r["latency_ms"] for r in system_rows)
        total_tokens = sum(r["tokens_total"] for r in system_rows)
        avg_cost = statistics.mean(r["cost_usd"] for r in system_rows)
        print(f"{system}: pass_rate={pass_rate:.0%} p50_latency_ms={p50_latency:.0f} "
              f"total_tokens={total_tokens} cost_per_request=${avg_cost:.5f}")


if __name__ == "__main__":
    asyncio.run(main())
