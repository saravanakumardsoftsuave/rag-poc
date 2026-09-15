"""Trajectory Metrics Engine (deliverable 2) + the pass/fail rule used by
both trajectory_eval.py (deliverable 1) and the gap/mitigation scripts
(deliverables 3-5).

"Cost" here is total LLM tokens (app.rag.count_tokens), not a dollar figure -
this project runs entirely on local models and has deliberately never
tracked a $ budget (see app/agent/safety.py's module docstring); tokens are
this codebase's real, existing notion of per-query cost, so that's what's
reported for the Cost Distribution metric instead of inventing a $/query
figure this project has no pricing model for.
"""

import statistics
from dataclasses import dataclass

from app.agent.state import AgentState
from evals.cases import TrajectoryCase


@dataclass
class CaseRun:
    case: TrajectoryCase
    result: dict  # the dict run_agent()/run_agent_with_state() returns
    state: AgentState
    outcome_pass: bool | None = None  # filled in by the llm_judge-based outcome eval
    outcome_verdict: str | None = None

    @property
    def tool_call_sequence(self) -> list[str]:
        return [step.tool for step in self.state.steps]

    @property
    def called_tools(self) -> set[str]:
        return set(self.tool_call_sequence)


def trajectory_passed(run: CaseRun) -> tuple[bool, str]:
    """The path-set assertion: required tools all ran, forbidden ones never
    did, and (for the one negative case) the agent actually refused instead
    of fabricating an answer. Never looks at answer text - that's the
    outcome eval's job, kept deliberately separate so the Gap in
    GAP_ANALYSIS.md means something."""
    case = run.case
    called = run.called_tools

    missing = case.required_tools - called
    if missing:
        return False, f"missing required tool call(s): {sorted(missing)}"

    present_forbidden = case.forbidden_tools & called
    if present_forbidden:
        return False, f"called forbidden tool(s): {sorted(present_forbidden)}"

    answered = run.result["stop_reason"] == "goal_completed"
    if case.expect_answered and not answered:
        return False, f"expected an answer, but agent stopped with {run.result['stop_reason']!r}"
    if not case.expect_answered and answered:
        return False, "expected a refusal (not in corpus), but the agent answered anyway"

    return True, "ok"


def tool_choice_accuracy(runs: list[CaseRun]) -> float:
    """% of tool-CALL steps (excludes answer/give_up, which aren't tool
    calls) that picked a tool considered valid for that case's query -
    across every step of every case, not per-case."""
    total = 0
    valid = 0
    for run in runs:
        valid_tools = run.case.tools_considered_valid()
        for step in run.state.steps:
            total += 1
            if step.tool in valid_tools:
                valid += 1
    return valid / total if total else 0.0


def argument_validity_rate(runs: list[CaseRun]) -> float:
    """% of tool calls whose arguments were valid, i.e. tools.py did not
    hand back an {"error": ...} dict (bad diet, unparseable "ingredient,
    diet" pair, unknown ingredient, or no substitute on file for that pair).
    search_knowledge_base has no invalid-argument shape (any string is a
    legal query), so every one of its calls counts as valid."""
    total = 0
    valid = 0
    for run in runs:
        for step in run.state.steps:
            total += 1
            result = step.result
            if isinstance(result, dict) and "error" in result:
                continue
            valid += 1
    return valid / total if total else 0.0


def step_efficiency(runs: list[CaseRun]) -> dict:
    """Ratio of actual tool-call steps taken to the optimal number, per
    case, plus the mean across the suite. 1.0 = optimal; >1.0 = took extra
    steps beyond the minimum needed."""
    per_case = {}
    for run in runs:
        actual = len(run.state.steps)
        per_case[run.case.id] = actual / run.case.optimal_tool_calls
    mean_ratio = statistics.mean(per_case.values()) if per_case else 0.0
    return {"per_case": per_case, "mean": mean_ratio}


def cost_distribution(runs: list[CaseRun]) -> dict:
    """p50 (median) and max total_tokens across the suite - a bare mean
    would hide a single runaway-loop query behind nine cheap ones."""
    token_counts = [run.state.total_tokens for run in runs]
    if not token_counts:
        return {"p50": 0, "max": 0, "per_case": {}}
    return {
        "p50": statistics.median(token_counts),
        "max": max(token_counts),
        "per_case": {run.case.id: run.state.total_tokens for run in runs},
    }


def outcome_pass_rate(runs: list[CaseRun]) -> float:
    graded = [run for run in runs if run.outcome_pass is not None]
    if not graded:
        return 0.0
    return sum(1 for run in graded if run.outcome_pass) / len(graded)


def trajectory_pass_rate(runs: list[CaseRun]) -> float:
    if not runs:
        return 0.0
    return sum(1 for run in runs if trajectory_passed(run)[0]) / len(runs)


def find_false_positive_traces(runs: list[CaseRun]) -> list[CaseRun]:
    """Outcome-vs-Trajectory Gap traces (deliverable 3): outcome PASSED but
    trajectory FAILED - the "right answer, flawed path" cases."""
    return [run for run in runs if run.outcome_pass is True and not trajectory_passed(run)[0]]
