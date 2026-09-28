"""Budget enforcement for the agentic loop: max iterations, max cumulative
tokens, max nominal cost, and a wall-clock timeout. All four are checked at
the top of every loop iteration - not just once, and not just on the final
call - so a multi-turn request's true per-lap token spend is counted.

Known limitation (documented, not silently papered over): the wall-clock
check only fires BETWEEN turns. A single call into the local generation
pipeline is synchronous and not preemptible, so one pathologically slow
generation could overshoot timeout_s before the next check runs.
"""

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Nominal only - the generation model runs locally and has no real per-token
# API cost. This constant exists purely so "cost per request" is a reportable
# number for the W7 race, not a claim about actual spend.
NOMINAL_USD_PER_1K_TOKENS = 0.002


@dataclass
class Budgets:
    max_iterations: int = 6
    max_tokens: int = 4000
    max_cost_usd: float = 0.05
    timeout_s: float = 60.0


class BudgetExceeded(Exception):
    def __init__(self, budget: str):
        self.budget = budget
        super().__init__(f"budget exceeded: {budget}")


class BudgetTracker:
    def __init__(self, budgets: Budgets, request_id: str = ""):
        self.budgets = budgets
        self.request_id = request_id
        self.iterations = 0
        self.tokens = 0
        self._start = time.monotonic()

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self._start

    @property
    def cost_usd(self) -> float:
        return self.tokens * NOMINAL_USD_PER_1K_TOKENS / 1000

    def add_tokens(self, n: int) -> None:
        self.tokens += n

    def check(self) -> None:
        """Raises BudgetExceeded on the first breached budget, checked in a
        fixed order so the reported reason is deterministic."""
        self.iterations += 1
        if self.iterations > self.budgets.max_iterations:
            raise BudgetExceeded("max_iterations")
        if self.tokens > self.budgets.max_tokens:
            raise BudgetExceeded("max_tokens")
        if self.cost_usd > self.budgets.max_cost_usd:
            raise BudgetExceeded("max_cost_usd")
        if self.elapsed_s > self.budgets.timeout_s:
            raise BudgetExceeded("timeout_s")

    def log_exceeded(self, budget: str) -> None:
        logger.warning(
            "agent_budget_exceeded request_id=%s budget=%s iterations=%d tokens=%d "
            "cost_usd=%.4f elapsed_s=%.2f",
            self.request_id, budget, self.iterations, self.tokens, self.cost_usd, self.elapsed_s,
        )
