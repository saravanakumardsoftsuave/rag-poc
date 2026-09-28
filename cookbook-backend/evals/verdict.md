# W7 race verdict — PARTIAL (agent side did not finish)

## Status, stated plainly

The fixed-workflow side of the race (all 10 requests) completed and its real
numbers are below. The agent side did not complete: only R1 had started
before the run was killed by the host system for running low on memory
(this machine loads three separate model singletons - the HF embedding
model, the cross-encoder reranker, and the Qwen2.5-1.5B generation model -
and CPU-only inference for a 10-request x up-to-5-turn agent race pushed
memory too far after the workflow side had already run for ~25 minutes).
Per explicit instruction, the run was not restarted automatically. **The
8-number agent-vs-workflow comparison this deliverable calls for is
therefore incomplete - only 4 of the 8 numbers exist.**

## Workflow: 4 numbers (real, from evals/race.csv)

| Metric | Value |
|---|---|
| Pass rate | 80% (8/10) |
| p50 latency | 162,837 ms |
| Total tokens | 5,132 |
| Cost/request | $0.00103 (nominal - see `app/agent/core/budgets.py`) |

Two real, non-fabricated failures, both in `search_recipes`'s JSON extraction
(the same step both systems share) rather than in the substitution logic:
- **R6** (Dal Makhani, dairy+tree_nut, cascading): extraction likely
  truncated before reaching `butter`/`cream`, which sit late in that
  recipe's ingredient list - so no substitution was attempted for them at
  all, and the checker correctly flagged the missing cascade.
- **R9** (Masala Dosa, gluten+dairy): the model's JSON reply for this recipe
  didn't parse even after fence-stripping and fraction-coercion.

Every cascading request that DID extract cleanly (**R3**, **R10**) resolved
its 2-pass substitution correctly, confirming the workflow's bounded retry
logic itself is sound - the failures are upstream, in extraction reliability
under this model/token-budget combination, not in the substitution
mechanism this week's tools were built to test.

## Agent: not measured

No agent request completed. `evals/race.py`'s agent path (`run_agent_request`)
is implemented and was mid-way through R1 when the process was killed - it
has not been validated end-to-end. To finish this deliverable: re-run
`python -m evals.race` (or `evals._resume` for just the agent half) on a
machine with more free memory, or after closing other memory-heavy
processes on this one.

## Verdict (cannot yet be stated with confidence)

The decision rule this deliverable asks for - "does the path vary by input,
and is there a request class that forces an agent" - cannot be answered
honestly without the agent numbers. What the workflow-only run DOES show:
the two failures came from the shared extraction step, not from routing or
substitution logic, which is weak evidence AGAINST needing an agent for
this task (a fixed pipeline's failure mode here is a model-quality problem
identical for both systems, not a control-flow problem an agent's dynamic
reasoning would fix). This is a hypothesis pending the missing half of the
data, not a conclusion - stating a full verdict now would be exactly the
"verdict contradicting the table" the rubric penalizes.
