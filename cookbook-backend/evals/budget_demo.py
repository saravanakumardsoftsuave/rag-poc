"""W7 requirement 4: a reproducible run that deliberately trips a budget and
terminates cleanly (no exception, no infinite spin). Uses a real
recipe-adaptation request that needs at least 3 turns (search_recipes, then
substitute_ingredient at least once, then FINAL) but caps max_iterations at 2
- so it trips the SAME iteration budget on every run, rather than hoping the
model happens to spin.
"""

import asyncio
import logging

from app.agent.core.budgets import Budgets
from app.agent.core.loop import run_agentic_loop
from app.agent.core.registry import local_registry
from app.agent.tools.recipe_tools import get_nutrition, search_recipes, substitute_ingredient
from evals.race import build_agent_task
from evals.requests import REQUESTS

LOG_PATH = "evals/budget_termination.log"


async def main():
    handler = logging.FileHandler(LOG_PATH, mode="w")
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.getLogger("app.agent.core.budgets").addHandler(handler)
    logging.getLogger("app.agent.core.budgets").setLevel(logging.WARNING)

    request = REQUESTS[2]  # R3: Paneer Butter Masala, dairy+tree_nut, needs search + >=2 substitutions
    tight_budgets = Budgets(max_iterations=2, max_tokens=100_000, max_cost_usd=100.0, timeout_s=600.0)
    registry = local_registry(search_recipes, get_nutrition, substitute_ingredient)

    result = await run_agentic_loop(build_agent_task(request), registry, tight_budgets, request_id=request.id)
    print("result status:", result["status"])
    if result["status"] == "budget_exceeded":
        print(f"Budget '{result['budget']}' fired cleanly after {result['iterations_used']} iterations, "
              f"no exception raised. Log written to {LOG_PATH}.")
    else:
        print("WARNING: this run did not hit the budget - it finished as", result["status"],
              "before the iteration cap. Re-run or lower max_iterations further.")


if __name__ == "__main__":
    asyncio.run(main())
