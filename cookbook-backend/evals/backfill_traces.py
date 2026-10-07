"""W11: populate logs/traces.jsonl with real request history we already have
on disk from the W7 and W10 races, instead of burning fresh (slow, this
machine has repeatedly crashed loading the local model under memory
pressure) LLM calls just to generate log volume to search through. Every
record here is honestly tagged with its real source - this is backfilled
historical data, not fabricated to pad the log.

Run with: python -m evals.backfill_traces
"""

import csv
import json
from pathlib import Path

from app.observability.tracer import Trace, write_trace

EVALS_DIR = Path(__file__).parent


def backfill_w7_race() -> int:
    """evals/race.csv - W7's fixed-workflow arm, 10 real requests."""
    path = EVALS_DIR / "race.csv"
    if not path.exists():
        return 0
    count = 0
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            trace = Trace(
                input_type="recipe_adaptation",
                question=f"[W7 workflow race] {row['request_id']}",
                prompt_version="v1",
                source="backfilled_from_w7_race.csv",
            )
            trace.add_span(
                name=f"workflow:{row['request_id']}",
                latency_ms=float(row["latency_ms"]),
                tokens=int(row["tokens_total"]),
                cost_usd=float(row["cost_usd"]),
            )
            trace.finish(
                answer=f"system=workflow passed={row['passed']}",
                status="ok" if row["passed"] == "True" else "failed",
            )
            count += 1
    return count


def backfill_w10_race() -> int:
    """evals/race_multiagent_checkpoint.jsonl - W10's single-agent and
    orchestrator arms, 20 real requests."""
    path = EVALS_DIR / "race_multiagent_checkpoint.jsonl"
    if not path.exists():
        return 0
    count = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            trace = Trace(
                input_type="recipe_adaptation",
                question=f"[W10 {row['system']} race] {row['request_id']}",
                prompt_version="v1",
                source="backfilled_from_w10_race_checkpoint.jsonl",
            )
            trace.add_span(
                name=f"{row['system']}:{row['request_id']}",
                latency_ms=float(row["latency_ms"]),
                tokens=int(row["tokens_total"]),
                cost_usd=float(row["cost_usd"]),
            )
            trace.finish(
                answer=row.get("final_answer_text", f"system={row['system']} passed={row['passed']}"),
                status="ok" if row["passed"] else "failed",
            )
            count += 1
    return count


if __name__ == "__main__":
    n7 = backfill_w7_race()
    n10 = backfill_w10_race()
    print(f"Backfilled {n7} traces from W7 race, {n10} traces from W10 race -> {n7 + n10} total.")
