# W10 race table - single agent vs. multi-agent orchestrator

Same 10 cases for both arms (this repo's `evals/requests.py`, unmodified): R1, R2, R3, R4, R5, R6, R7, R8, R9, R10.

| System | Pass rate | p50 latency (ms) | p99 latency (ms) | Total tokens | Cost/question (USD) |
|---|---|---|---|---|---|
| single agent | 0% | 28460 | 245253 | 3567 | $0.00071 |
| orchestrator | 0% | 240577 | 368517 | 17572 | $0.00351 |

**Note on p99:** with n=10 samples per arm, p99 is not a statistically robust estimate - it is the ~99th-ranked interpolated value and sits at or very near the observed maximum. Reported as required, not presented as a reliable tail estimate.

**Context re-send multiplier:** 4.9x (orchestrator total tokens 17572 / single-agent total tokens 3567).
Attributed to: **orchestrator->allergen_worker** (9206 tokens, 52% of all multi-agent tokens across every hand-off in `handoffs.log`).
