"""Trajectory Eval Suite (deliverable 1): 10 real cookbook-agent queries,
each asserting the *path* taken (which tools ran) rather than the answer
text - see tests/test_e2e.py for the outcome-only equivalent this
deliberately does not duplicate.

Real agent, real Pinecone, real local generation model - same "opt-in, not
run by default" pattern as tests/test_e2e.py (see pytest.ini): a single case
here runs the full decide-tool-observe loop through a live model, so this
suite is slow and is not part of the default `pytest` run.

    pytest evals/trajectory_eval.py -m trajectory -v

Flexible assertions: cases assert a *set* of required tools (see
evals/cases.py's `required_tools`/`forbidden_tools`), not one fixed call
sequence - e.g. an allergen question about a multi-ingredient dish accepts
whichever ingredient the agent legitimately checked, and only fails if no
allergen lookup ran at all, or if outright wrong tools were called.
"""

import pytest

from evals.cases import CASES
from evals.harness import run_case
from evals.metrics import trajectory_passed

pytestmark = pytest.mark.trajectory


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_trajectory(case):
    run = run_case(case, judge=False)
    passed, reason = trajectory_passed(run)

    print(f"\n[{case.id}] tools called: {run.tool_call_sequence}")
    print(f"[{case.id}] stop_reason: {run.result['stop_reason']}")
    print(f"[{case.id}] answer: {run.result['answer']}")

    assert passed, (
        f"trajectory failed for {case.id!r}: {reason}\n"
        f"tools called: {run.tool_call_sequence}\n"
        f"stop_reason: {run.result['stop_reason']}"
    )
