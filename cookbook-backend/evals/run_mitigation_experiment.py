"""Deliverables 4 + 5: Single Mitigation Experiment & Cost Measurement, and
the Per-Mode Regression Matrix.

The ONE fix under test is app/agent/agent.py's grounding guard
(_forced_grounding_call): a deterministic check that forces
substitute_ingredient/get_allergen_profile to run before the agent is
allowed to answer a substitution/allergen question, if the question names an
ingredient those tables cover. It targets `tool_bypass` - the top failure
mode found by run_gap_analysis.py (the agent answering from pretrained
knowledge instead of the fixed tables).

Runs the same 10 cases twice - guard disabled ("before"), guard enabled
("after") - classifies every run against evals/failure_modes.py's taxonomy,
and reports:
  - the exact before -> after count change for tool_bypass
  - the exact token/latency price paid, for the case(s) where the guard
    actually fired
  - a full per-mode regression table, flagging any mode that got worse or
    newly appeared

No llm_judge calls here (outcome text isn't what's being measured) - only
run_gap_analysis.py needs those, so this script is roughly half the model
calls of that one.

Usage: python -m evals.run_mitigation_experiment
"""

import logging
import sys
from pathlib import Path

import app.agent.agent as agent_module
from evals.cases import CASES
from evals.failure_modes import ALL_MODES, TOOL_BYPASS, classify, count_modes
from evals.harness import run_case
from evals.metrics import CaseRun

logging.basicConfig(level=logging.WARNING)

MITIGATION_REPORT_PATH = Path(__file__).parent / "MITIGATION_RESULTS.md"
REGRESSION_REPORT_PATH = Path(__file__).parent / "REGRESSION_MATRIX.md"


def _run_sweep(guard_enabled: bool) -> list[CaseRun]:
    agent_module.GROUNDING_GUARD_ENABLED = guard_enabled
    return [run_case(case, judge=False) for case in CASES]


def _by_id(runs: list[CaseRun]) -> dict[str, CaseRun]:
    return {run.case.id: run for run in runs}


def main() -> int:
    print("Sweep 1/2: grounding guard DISABLED (before)...")
    before_runs = _run_sweep(guard_enabled=False)
    print("Sweep 2/2: grounding guard ENABLED (after)...")
    after_runs = _run_sweep(guard_enabled=True)

    before_by_id = _by_id(before_runs)
    after_by_id = _by_id(after_runs)

    before_counts = count_modes(before_runs)
    after_counts = count_modes(after_runs)

    # --- deliverable 4: the single mitigation's before/after + price paid ---
    before_bypass = before_counts[TOOL_BYPASS]
    after_bypass = after_counts[TOOL_BYPASS]

    fixed_cases = [
        case_id
        for case_id, before_run in before_by_id.items()
        if TOOL_BYPASS in classify(before_run) and TOOL_BYPASS not in classify(after_by_id[case_id])
    ]

    price_rows = []
    total_token_delta = 0
    total_latency_delta = 0.0
    for case_id in fixed_cases:
        before_run = before_by_id[case_id]
        after_run = after_by_id[case_id]
        token_delta = after_run.state.total_tokens - before_run.state.total_tokens
        latency_delta = after_run.state.elapsed_time - before_run.state.elapsed_time
        total_token_delta += token_delta
        total_latency_delta += latency_delta
        price_rows.append(
            f"| {case_id} | {before_run.state.total_tokens} | {after_run.state.total_tokens} "
            f"| {token_delta:+d} | {before_run.state.elapsed_time:.1f}s | {after_run.state.elapsed_time:.1f}s "
            f"| {latency_delta:+.1f}s |"
        )

    mitigation_lines = [
        "# Single Mitigation Experiment",
        "",
        "**Fix applied:** `app/agent/agent.py`'s `_forced_grounding_call` guard - a deterministic "
        "check that forces `substitute_ingredient`/`get_allergen_profile` to run, for a question "
        "naming an ingredient those tables cover, before the agent is allowed to finalize an "
        "answer. This is a hard step requirement / deterministic workflow substitution, not a "
        "prompt tweak - see the function's docstring for the full rationale.",
        "",
        "**Target failure mode:** `tool_bypass` (the agent answering a substitution/allergen "
        "question from its own pretrained knowledge instead of the fixed lookup tables).",
        "",
        "## Before -> After",
        "",
        f"- `tool_bypass` count across all 10 cases: **{before_bypass} -> {after_bypass}** "
        f"({after_bypass - before_bypass:+d})",
        f"- Cases fixed: {', '.join(fixed_cases) if fixed_cases else '(none)'}",
        "",
        "## Measured price paid",
        "",
        "Exact token/latency delta for each case where the guard actually fired (forced one "
        "extra tool call plus one extra decide-loop iteration afterward):",
        "",
        "| case | tokens before | tokens after | token delta | latency before | latency after | latency delta |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *price_rows,
        "",
        f"**Total added tokens across fixed cases: {total_token_delta:+d}**",
        f"**Total added wall-clock latency across fixed cases: {total_latency_delta:+.1f}s**",
        "",
        "No price is paid on cases the guard never fires for (no covered ingredient named in the "
        "question, or the tool already ran) - only rows above changed at all.",
    ]
    MITIGATION_REPORT_PATH.write_text("\n".join(mitigation_lines), encoding="utf-8")

    # --- deliverable 5: full per-mode regression matrix ---
    regression_lines = [
        "# Per-Mode Regression Matrix",
        "",
        "Every failure mode in the taxonomy (evals/failure_modes.py), counted across all 10 "
        "cases, before vs. after the grounding guard.",
        "",
        "| failure mode | before | after | delta | verdict |",
        "| --- | --- | --- | --- | --- |",
    ]
    worsened = []
    emerged = []
    for mode in ALL_MODES:
        before_n = before_counts[mode]
        after_n = after_counts[mode]
        delta = after_n - before_n
        if delta > 0 and before_n == 0:
            verdict = "**NEW - emerged after the fix**"
            emerged.append(mode)
        elif delta > 0:
            verdict = "**WORSENED**"
            worsened.append(mode)
        elif delta < 0:
            verdict = "improved"
        else:
            verdict = "unchanged"
        regression_lines.append(f"| {mode} | {before_n} | {after_n} | {delta:+d} | {verdict} |")

    regression_lines += ["", "## Side effects"]
    if worsened or emerged:
        if worsened:
            regression_lines.append(f"- Worsened: {', '.join(worsened)}")
        if emerged:
            regression_lines.append(f"- Newly emerged: {', '.join(emerged)}")
    else:
        regression_lines.append("- None: no failure mode worsened and none newly appeared.")

    regression_lines += ["", "## Per-case mode detail", "", "| case | before | after |", "| --- | --- | --- |"]
    for case in CASES:
        before_modes = sorted(classify(before_by_id[case.id])) or ["(none)"]
        after_modes = sorted(classify(after_by_id[case.id])) or ["(none)"]
        regression_lines.append(f"| {case.id} | {', '.join(before_modes)} | {', '.join(after_modes)} |")

    REGRESSION_REPORT_PATH.write_text("\n".join(regression_lines), encoding="utf-8")

    print(f"\nWrote {MITIGATION_REPORT_PATH}")
    print(f"Wrote {REGRESSION_REPORT_PATH}")
    print(f"tool_bypass: {before_bypass} -> {after_bypass}")
    print(f"Worsened modes: {worsened or 'none'}; newly emerged: {emerged or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
