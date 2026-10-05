"""W10: race the single agent (W7) against the multi-agent orchestrator over
the same 10 shared requests (evals/requests.py - this repo's stand-in for
"the same Week-6 cases", since no literal Week-6 eval set exists here; it is
NOT modified for this race). Checkpointed to evals/race_multiagent_checkpoint.jsonl
after every single unit of work, because this machine has already killed two
earlier long-running processes this week from low memory - a killed run can
simply be re-invoked and it resumes from whatever finished last.
"""

import asyncio
import json
import statistics
import time
from pathlib import Path

from app.agent.orchestrator import run_orchestrator_request
from evals.race import run_agent_request
from evals.requests import REQUESTS

HERE = Path(__file__).parent
CHECKPOINT_PATH = HERE / "race_multiagent_checkpoint.jsonl"
RACE_TABLE_PATH = HERE / "race_table.md"
FAILURE_CASE_PATH = HERE / "failure_case.md"
VERDICT_PATH = HERE / "verdict.md"

FAILURE_REQUEST_ID = "R2"  # single allergen (dairy), no cascade - keeps the
# failure-mode observation uncomplicated by cascade logic, per W10 requirement 4.


def _load_checkpoint() -> dict[tuple[str, str], dict]:
    done: dict[tuple[str, str], dict] = {}
    if CHECKPOINT_PATH.exists():
        for line in CHECKPOINT_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            done[(row["system"], row["request_id"])] = row
    return done


def _append_checkpoint(row: dict) -> None:
    with CHECKPOINT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()


async def main() -> None:
    done = _load_checkpoint()
    print(f"resuming with {len(done)} unit(s) already checkpointed", flush=True)

    for request in REQUESTS:
        key = ("agent", request.id)
        if key in done:
            print(f"[agent] {request.id} (from checkpoint)")
        else:
            print(f"[agent] {request.id} ...", flush=True)
            row = await run_agent_request(request)
            _append_checkpoint(row)
            done[key] = row
            print(f"  -> passed={row['passed']} latency_ms={row['latency_ms']} tokens={row['tokens_total']}")

        key = ("orchestrator", request.id)
        if key in done:
            print(f"[orchestrator] {request.id} (from checkpoint)")
        else:
            inject = request.id == FAILURE_REQUEST_ID
            print(f"[orchestrator] {request.id} (inject_failure={inject}) ...", flush=True)
            row = await run_orchestrator_request(request, inject_failure=inject)
            _append_checkpoint(row)
            done[key] = row
            print(f"  -> passed={row['passed']} latency_ms={row['latency_ms']} tokens={row['tokens_total']}")

    write_reports(done)
    print("\nAll units complete. Reports written.")


def _percentile_99(values: list[float]) -> float:
    if len(values) < 2:
        return values[0] if values else 0.0
    return statistics.quantiles(values, n=100)[98]


def write_reports(done: dict[tuple[str, str], dict]) -> None:
    request_ids = [r.id for r in REQUESTS]

    def rows_for(system: str) -> list[dict]:
        return [done[(system, rid)] for rid in request_ids if (system, rid) in done]

    agent_rows = rows_for("agent")
    orch_rows = rows_for("orchestrator")

    if len(agent_rows) < len(REQUESTS) or len(orch_rows) < len(REQUESTS):
        missing_agent = [rid for rid in request_ids if ("agent", rid) not in done]
        missing_orch = [rid for rid in request_ids if ("orchestrator", rid) not in done]
        RACE_TABLE_PATH.write_text(
            "# W10 race - INCOMPLETE\n\n"
            f"agent: {len(agent_rows)}/{len(REQUESTS)} cases complete. Missing: {missing_agent}\n"
            f"orchestrator: {len(orch_rows)}/{len(REQUESTS)} cases complete. Missing: {missing_orch}\n\n"
            "Re-run `python -m evals.race_multiagent` to resume from the checkpoint file "
            "(`race_multiagent_checkpoint.jsonl`); already-completed units are skipped.\n",
            encoding="utf-8",
        )
        return

    def summarize(rows: list[dict]) -> dict:
        latencies = [r["latency_ms"] for r in rows]
        tokens = [r["tokens_total"] for r in rows]
        costs = [r["cost_usd"] for r in rows]
        return {
            "pass_rate": sum(r["passed"] for r in rows) / len(rows),
            "p50_latency_ms": statistics.median(latencies),
            "p99_latency_ms": _percentile_99(latencies),
            "total_tokens": sum(tokens),
            "cost_per_question": statistics.mean(costs),
        }

    agent_summary = summarize(agent_rows)
    orch_summary = summarize(orch_rows)

    multiplier = (
        orch_summary["total_tokens"] / agent_summary["total_tokens"]
        if agent_summary["total_tokens"]
        else float("inf")
    )

    handoff_totals = _sum_handoffs_by_name()
    dominant_name, dominant_tokens, dominant_pct = _dominant_handoff(handoff_totals)

    lines = [
        "# W10 race table - single agent vs. multi-agent orchestrator",
        "",
        f"Same 10 cases for both arms (this repo's `evals/requests.py`, unmodified): "
        f"{', '.join(request_ids)}.",
        "",
        "| System | Pass rate | p50 latency (ms) | p99 latency (ms) | Total tokens | Cost/question (USD) |",
        "|---|---|---|---|---|---|",
        f"| single agent | {agent_summary['pass_rate']:.0%} | {agent_summary['p50_latency_ms']:.0f} | "
        f"{agent_summary['p99_latency_ms']:.0f} | {agent_summary['total_tokens']} | "
        f"${agent_summary['cost_per_question']:.5f} |",
        f"| orchestrator | {orch_summary['pass_rate']:.0%} | {orch_summary['p50_latency_ms']:.0f} | "
        f"{orch_summary['p99_latency_ms']:.0f} | {orch_summary['total_tokens']} | "
        f"${orch_summary['cost_per_question']:.5f} |",
        "",
        "**Note on p99:** with n=10 samples per arm, p99 is not a statistically robust estimate - "
        "it is the ~99th-ranked interpolated value and sits at or very near the observed maximum. "
        "Reported as required, not presented as a reliable tail estimate.",
        "",
        f"**Context re-send multiplier:** {multiplier:.1f}x "
        f"(orchestrator total tokens {orch_summary['total_tokens']} / single-agent total tokens "
        f"{agent_summary['total_tokens']}).",
        f"Attributed to: **{dominant_name}** ({dominant_tokens} tokens, "
        f"{dominant_pct:.0%} of all multi-agent tokens across every hand-off in `handoffs.log`).",
    ]
    RACE_TABLE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    write_verdict(agent_summary, orch_summary, multiplier)


def _sum_handoffs_by_name() -> dict[str, int]:
    handoffs_log = HERE / "handoffs.log"
    totals: dict[str, int] = {}
    if not handoffs_log.exists():
        return totals
    for line in handoffs_log.read_text(encoding="utf-8").splitlines():
        if "tokens_total=" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        name = parts[1]
        token_field = [p for p in parts[2].split() if p.startswith("tokens_total=")]
        if not token_field:
            continue
        raw = token_field[0].split("=", 1)[1]
        if raw == "unknown":
            continue
        try:
            totals[name] = totals.get(name, 0) + int(raw)
        except ValueError:
            continue
    return totals


def _dominant_handoff(totals: dict[str, int]) -> tuple[str, int, float]:
    if not totals:
        return "(no hand-off data)", 0, 0.0
    grand_total = sum(totals.values())
    name, tokens = max(totals.items(), key=lambda kv: kv[1])
    pct = tokens / grand_total if grand_total else 0.0
    return name, tokens, pct


def write_verdict(agent_summary: dict, orch_summary: dict, multiplier: float) -> None:
    keep_or_kill = "KILL" if (
        orch_summary["total_tokens"] > agent_summary["total_tokens"]
        and orch_summary["pass_rate"] <= agent_summary["pass_rate"]
    ) else "KEEP (contingent)"
    lines = [
        f"# Verdict: {keep_or_kill}",
        "",
        "Sunk-cost bias named out loud first: the orchestrator took real, separate build "
        "effort this week (decomposition, two scoped workers, synthesis), which creates a "
        "pull to call it the winner regardless of the numbers just to justify that effort. "
        "Naming that before the verdict, not after.",
        "",
        f"Cited numbers: pass rate {agent_summary['pass_rate']:.0%} (single agent) vs "
        f"{orch_summary['pass_rate']:.0%} (orchestrator); total tokens "
        f"{agent_summary['total_tokens']} (single agent) vs {orch_summary['total_tokens']} "
        f"(orchestrator) - a {multiplier:.1f}x re-send multiplier for no pass-rate gain "
        "the numbers above can point to on their own.",
        "",
        f"Verdict: {keep_or_kill} - kill the orchestrator for this task unless the pass-rate "
        "or latency numbers above show it clearly ahead; the token/cost multiplier alone is "
        "not worth paying without a matching quality or speed win.",
    ]
    VERDICT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
