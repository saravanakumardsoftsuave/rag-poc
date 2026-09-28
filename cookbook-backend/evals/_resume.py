"""One-off resume script: R1-R8 workflow results are already known from the
prior run's live output (captured before a stale Neon/Postgres connection
killed the process at R9 - fixed now via pool_pre_ping=True in
app/database.py). This finishes R9-R10 workflow plus all 10 agent requests
and writes them to race_resume.csv; the caller merges with the known R1-R8
workflow rows into the final race.csv."""

import asyncio
import csv
from pathlib import Path

from evals.race import run_agent_request, run_workflow_request
from evals.requests import REQUESTS


async def main():
    rows = []
    for request in REQUESTS[8:]:  # R9, R10
        print(f"[workflow] {request.id} ...", flush=True)
        wf = run_workflow_request(request)
        print(f"  -> passed={wf['passed']} latency_ms={wf['latency_ms']} tokens={wf['tokens_total']} problems={wf['problems']}")
        rows.append(wf)

    for request in REQUESTS:
        print(f"[agent] {request.id} ...", flush=True)
        ag = await run_agent_request(request)
        print(f"  -> passed={ag['passed']} latency_ms={ag['latency_ms']} tokens={ag['tokens_total']} problems={ag['problems']}")
        rows.append(ag)

    out_path = Path(__file__).parent / "race_resume.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["system", "request_id", "passed", "latency_ms", "tokens_total", "cost_usd"])
        for row in rows:
            writer.writerow([row["system"], row["request_id"], row["passed"], row["latency_ms"],
                              row["tokens_total"], row["cost_usd"]])
    print("done ->", out_path)


if __name__ == "__main__":
    asyncio.run(main())
