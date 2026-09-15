"""Shared runner: executes one TrajectoryCase against the real agent and the
real llm_judge, and packages the result as a CaseRun. Used by
trajectory_eval.py, run_gap_analysis.py, and run_mitigation_experiment.py so
none of them re-implement "run the agent, then judge the answer."
"""

import logging

from app.agent.agent import run_agent_with_state
from app.config import settings
from evals.cases import CASES, TrajectoryCase
from evals.metrics import CaseRun
from tests.llm_judge import JUDGE_PROMPT

logger = logging.getLogger(__name__)

# This suite runs the real decide-tool-observe loop (plus llm_judge, itself
# another generation call) through a live model, times 10 cases, sometimes
# twice per script (before/after). On this project's CPU-only dev hardware,
# the configured production model (Qwen2.5-1.5B-Instruct) took 100+ seconds
# for a single query and blew past the agent's own 60s MAX_EXECUTION_TIME
# safety limit before finishing one decide step - useless for trajectory
# data, since every case would fail on hardware slowness rather than real
# agent behavior. Qwen2.5-0.5B-Instruct (already cached locally, same family,
# same prompts/tools) brings that down to the tens of seconds.
#
# Retrieval settings are also trimmed for the same reason: the final-answer
# prompt embeds every retrieved chunk's full text verbatim (see agent.py's
# _finalize_answer), so hybrid_top_k=20 (production default) means ~5000
# tokens of context per query - most of one case's wall-clock time on this
# hardware is CPU prefill over that context, not the actual decision-making
# this suite measures. Trimmed to enough chunks to still answer every case
# correctly (verified below) without paying for context depth this suite has
# no use for.
#
# All of this only affects these eval scripts' own process-local settings -
# it never touches the settings the running app or its own test suite use.
settings.hf_generation_model = "Qwen/Qwen2.5-0.5B-Instruct"
settings.hf_generation_max_new_tokens = 120
settings.hybrid_top_k = 6
settings.rerank_candidate_pool = 15

# The outcome (llm_judge) eval deliberately does NOT reuse the 0.5B model
# above: tried head-to-head on two answers that plainly satisfy their
# expected_facts (a correct "toor dal" answer, a correct "margarine or
# coconut oil" answer), the 0.5B judge failed both with a bare "FAIL" and no
# stated reason - not a borderline call, just not capable enough at this
# size to follow the judge prompt's instructions reliably. That would make
# Outcome Pass Rate (and therefore the Gap) measure judge quality, not agent
# quality. Qwen2.5-1.5B-Instruct judged both correctly in ~10s each (no
# decide-loop, no large retrieved-chunk context - just one short judge
# prompt), so it's used here for judging only, as its own separate cached
# pipeline instance alongside the 0.5B agent model.
_judge_generator = None


def _get_judge_generator():
    global _judge_generator
    if _judge_generator is None:
        from transformers import pipeline

        _judge_generator = pipeline("text-generation", model="Qwen/Qwen2.5-1.5B-Instruct")
    return _judge_generator


def judge_case_answer(question: str, answer: str, expected_facts: str) -> tuple[bool, str]:
    prompt = JUDGE_PROMPT.format(question=question, expected_facts=expected_facts, answer=answer)
    output = _get_judge_generator()([{"role": "user", "content": prompt}], max_new_tokens=120, do_sample=False)
    verdict = output[0]["generated_text"][-1]["content"].strip()
    first_line = verdict.splitlines()[0] if verdict else ""
    passed = first_line.strip().upper().startswith("PASS")
    return passed, verdict


def run_case(case: TrajectoryCase, judge: bool = True) -> CaseRun:
    logger.info("[EVAL] Running case %r: %s", case.id, case.question)
    result, state = run_agent_with_state(case.question)
    run = CaseRun(case=case, result=result, state=state)

    if judge:
        passed, verdict = judge_case_answer(
            question=case.question,
            answer=result["answer"],
            expected_facts=case.expected_facts,
        )
        run.outcome_pass = passed
        run.outcome_verdict = verdict

    return run


def run_all_cases(judge: bool = True) -> list[CaseRun]:
    return [run_case(case, judge=judge) for case in CASES]
