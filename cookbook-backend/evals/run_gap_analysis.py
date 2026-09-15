"""Deliverable 3: Gap Analysis & Trace Expose.

Runs all 10 cases against the pre-mitigation agent (the grounding guard added
for deliverable 4 is disabled here on purpose - this script's job is to
discover the Outcome-vs-Trajectory Gap as it existed *before* any fix, the
same way trajectory_eval.py or a real user would have hit it). Deliverable 4
then measures what the guard changes; see run_mitigation_experiment.py.

Writes GAP_ANALYSIS.md with:
  - Gap = Outcome Pass Rate - Trajectory Pass Rate
  - the four Trajectory Metrics Engine numbers (deliverable 2)
  - a full execution trace of one query that passed outcome but failed
    trajectory (a "right answer, flawed path" case)

Usage: python -m evals.run_gap_analysis
"""

import logging
import sys
from pathlib import Path

import app.agent.agent as agent_module
from evals.cases import CASES
from evals.harness import run_case
from evals.metrics import (
    argument_validity_rate,
    cost_distribution,
    find_false_positive_traces,
    outcome_pass_rate,
    step_efficiency,
    tool_choice_accuracy,
    trajectory_passed,
    trajectory_pass_rate,
)

logging.basicConfig(level=logging.WARNING)  # quiet the agent's own [AGENT]/[TOOL] logs for this report
REPORT_PATH = Path(__file__).parent / "GAP_ANALYSIS.md"


def _format_trace(run) -> str:
    lines = [f"### False-positive trace: `{run.case.id}`", "", f"**Question:** {run.case.question}", ""]
    lines.append("**Tool calls made:**")
    for step in run.state.steps:
        lines.append(f"{step.step}. `{step.tool}({step.arguments})` -> `{step.result}`")
    lines.append("")
    lines.append(f"**Stop reason:** `{run.result['stop_reason']}`")
    lines.append("")
    lines.append(f"**Final answer:** {run.result['answer']}")
    lines.append("")
    _, reason = trajectory_passed(run)
    lines.append(f"**Why the trajectory eval fails this:** {reason}")
    lines.append("")
    lines.append(f"**Why the outcome eval passes this:** {run.outcome_verdict}")
    return "\n".join(lines)


def main() -> int:
    print("Running 10 cases with the grounding guard DISABLED (pre-mitigation baseline)...")
    agent_module.GROUNDING_GUARD_ENABLED = False
    runs = [run_case(case, judge=True) for case in CASES]

    outcome_rate = outcome_pass_rate(runs)
    trajectory_rate = trajectory_pass_rate(runs)
    gap = outcome_rate - trajectory_rate

    tool_acc = tool_choice_accuracy(runs)
    arg_validity = argument_validity_rate(runs)
    steps = step_efficiency(runs)
    costs = cost_distribution(runs)

    false_positives = find_false_positive_traces(runs)

    lines = [
        "# Gap Analysis & Trace Expose",
        "",
        f"10 cases, real agent (`app/agent/agent.py`), grounding guard **disabled** "
        f"(pre-mitigation baseline - see run_mitigation_experiment.py for the guard's effect).",
        "",
        "## Outcome-vs-Trajectory Gap",
        "",
        f"- Outcome Pass Rate: **{outcome_rate:.0%}** ({sum(1 for r in runs if r.outcome_pass)}/{len(runs)})",
        f"- Trajectory Pass Rate: **{trajectory_rate:.0%}** ({sum(1 for r in runs if trajectory_passed(r)[0])}/{len(runs)})",
        f"- **Gap = {gap:+.0%}**",
        "",
        "## Trajectory Metrics Engine",
        "",
        f"- Tool-Choice Accuracy: **{tool_acc:.0%}**",
        f"- Argument Validity Rate: **{arg_validity:.0%}**",
        f"- Step Efficiency (actual/optimal, mean): **{steps['mean']:.2f}**",
        f"- Cost Distribution (tokens): p50=**{costs['p50']}**, max=**{costs['max']}**",
        "",
        "### Per-case detail",
        "",
        "| case | tools called | stop_reason | outcome | trajectory | tokens |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for run in runs:
        traj_ok, _ = trajectory_passed(run)
        lines.append(
            f"| {run.case.id} | {', '.join(run.tool_call_sequence) or '(none)'} "
            f"| {run.result['stop_reason']} | {'PASS' if run.outcome_pass else 'FAIL'} "
            f"| {'PASS' if traj_ok else 'FAIL'} | {run.state.total_tokens} |"
        )

    lines += ["", "## False-positive trace(s)", ""]
    if false_positives:
        for run in false_positives:
            lines.append(_format_trace(run))
            lines.append("")
    else:
        lines.append("(none found in this run)")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {REPORT_PATH}")
    print(f"Gap = {gap:+.0%}  (outcome {outcome_rate:.0%} - trajectory {trajectory_rate:.0%})")
    print(f"False-positive traces found: {len(false_positives)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
