"""Structured request tracing (W11). Every request gets one JSON-line record
in logs/traces.jsonl: trace_id, timestamp, prompt_version, input_type, the
question AND the answer text (the common mistake this guards against is
indexing only inputs - a complaint about a bad *output* needs the output
searchable too), per-span latency/tokens/cost, and retrieved context ids.

This is deliberately a flat, greppable JSON-lines file, not a tracing
backend - the point of W11's drill is "find it with jq/grep on a log field",
not "stand up Jaeger"."""

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "traces.jsonl"

NOMINAL_USD_PER_1K_TOKENS = 0.002


@dataclass
class Span:
    name: str
    latency_ms: float
    tokens: int = 0
    cost_usd: float = 0.0
    context_ids: list[str] = field(default_factory=list)


@dataclass
class Trace:
    input_type: str
    question: str
    prompt_version: str
    user: str = "anonymous"
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    spans: list[Span] = field(default_factory=list)
    answer: str = ""
    status: str = "ok"
    source: str = "live"

    def add_span(
        self,
        name: str,
        latency_ms: float,
        tokens: int = 0,
        cost_usd: float | None = None,
        context_ids: list[str] | None = None,
    ) -> None:
        if cost_usd is None:
            cost_usd = tokens * NOMINAL_USD_PER_1K_TOKENS / 1000
        self.spans.append(Span(name, latency_ms, tokens, cost_usd, context_ids or []))

    @contextmanager
    def span(self, name: str, tokens: int = 0, context_ids: list[str] | None = None):
        """Times a block of code as one span: `with trace.span("generation") as s: ...`"""
        start = time.perf_counter()
        record = {"tokens": tokens}
        yield record
        latency_ms = (time.perf_counter() - start) * 1000
        self.add_span(name, latency_ms, record.get("tokens", tokens), context_ids=context_ids)

    def retrieved_context_ids(self) -> list[str]:
        ids: list[str] = []
        for s in self.spans:
            ids.extend(s.context_ids)
        return ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "user": self.user,
            "prompt_version": self.prompt_version,
            "input_type": self.input_type,
            "question": self.question,
            "answer": self.answer,
            "status": self.status,
            "source": self.source,
            "spans": [
                {
                    "name": s.name,
                    "latency_ms": round(s.latency_ms, 1),
                    "tokens": s.tokens,
                    "cost_usd": round(s.cost_usd, 6),
                    "context_ids": s.context_ids,
                }
                for s in self.spans
            ],
            "retrieved_context_ids": self.retrieved_context_ids(),
            "total_latency_ms": round(sum(s.latency_ms for s in self.spans), 1),
            "total_tokens": sum(s.tokens for s in self.spans),
            "total_cost_usd": round(sum(s.cost_usd for s in self.spans), 6),
        }

    def finish(self, answer: str = "", status: str = "ok", log_path: Path = LOG_PATH) -> dict[str, Any]:
        self.answer = answer
        self.status = status
        record = self.to_dict()
        write_trace(record, log_path)
        return record


def write_trace(record: dict[str, Any], log_path: Path = LOG_PATH) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_traces(log_path: Path = LOG_PATH) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    with log_path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
