"""Failure-mode taxonomy used by the regression matrix (deliverable 5) and to
pick "the top failure mode" the single mitigation (deliverable 4) targets.

Each mode is a pure function of one CaseRun - no shared state, so the same
classifier runs identically over the before-guard and after-guard sweeps in
run_mitigation_experiment.py.
"""

from evals.metrics import CaseRun, trajectory_passed

TOOL_BYPASS = "tool_bypass"
WRONG_TOOL_CHOICE = "wrong_tool_choice"
ARGUMENT_HALLUCINATION = "argument_hallucination"
REPEATED_ACTION_STUCK = "repeated_action_stuck"
GAVE_UP_TOO_EARLY = "gave_up_too_early"
FABRICATION_WITHOUT_EVIDENCE = "fabrication_without_evidence"
STEP_INEFFICIENCY = "step_inefficiency"

ALL_MODES = [
    TOOL_BYPASS,
    WRONG_TOOL_CHOICE,
    ARGUMENT_HALLUCINATION,
    REPEATED_ACTION_STUCK,
    GAVE_UP_TOO_EARLY,
    FABRICATION_WITHOUT_EVIDENCE,
    STEP_INEFFICIENCY,
]


def classify(run: CaseRun) -> set[str]:
    """Every failure mode present in this one trajectory - usually zero or
    one, but a run can trip more than one at once (e.g. a wrong tool choice
    that also wastes a step)."""
    modes: set[str] = set()
    case = run.case
    called = run.called_tools
    answered = run.result["stop_reason"] == "goal_completed"

    grounding_tools_required = case.required_tools - {"search_knowledge_base"}
    if grounding_tools_required and not (grounding_tools_required & called) and answered:
        # Answered anyway despite skipping every tool that would have
        # grounded the answer against a fixed table - the bypass this
        # suite's mitigation targets.
        modes.add(TOOL_BYPASS)

    valid_tools = case.tools_considered_valid()
    if called - valid_tools:
        modes.add(WRONG_TOOL_CHOICE)

    for step in run.state.steps:
        if isinstance(step.result, dict) and "error" in step.result:
            modes.add(ARGUMENT_HALLUCINATION)

    if run.result["stop_reason"] == "repeated_action":
        modes.add(REPEATED_ACTION_STUCK)

    if case.expect_answered and not answered and TOOL_BYPASS not in modes:
        modes.add(GAVE_UP_TOO_EARLY)

    if not case.expect_answered and answered:
        modes.add(FABRICATION_WITHOUT_EVIDENCE)

    if len(run.state.steps) > case.optimal_tool_calls:
        modes.add(STEP_INEFFICIENCY)

    return modes


def count_modes(runs: list[CaseRun]) -> dict[str, int]:
    counts = dict.fromkeys(ALL_MODES, 0)
    for run in runs:
        for mode in classify(run):
            counts[mode] += 1
    return counts
