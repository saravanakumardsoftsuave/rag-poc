"""Agent state: everything carried across one question's tool-calling loop.

Mirrors the shape asked for - user_query, steps, tool_results,
retrieval_attempts, tool_calls, errors, elapsed_time, previous_actions -
plus a couple of fields (chunks, best_relevance_score, stop_reason) the loop
itself needs to track evidence quality and why it stopped.
"""

import time
from dataclasses import dataclass, field


@dataclass
class ActionRecord:
    step: int
    tool: str
    arguments: dict
    result: object


@dataclass
class AgentState:
    user_query: str
    steps: list[ActionRecord] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    retrieval_attempts: int = 0
    tool_calls: int = 0
    errors: int = 0
    previous_actions: list[tuple[str, str]] = field(default_factory=list)
    chunks: dict = field(default_factory=dict)
    best_relevance_score: float = 0.0
    total_tokens: int = 0
    stop_reason: str | None = None
    started_at: float = field(default_factory=time.monotonic)

    @property
    def elapsed_time(self) -> float:
        return time.monotonic() - self.started_at

    def record_step(self, tool: str, arguments: dict, result: object) -> None:
        self.steps.append(ActionRecord(step=len(self.steps) + 1, tool=tool, arguments=arguments, result=result))
        self.tool_results.append({"tool": tool, "arguments": arguments, "result": result})

    def to_dict(self) -> dict:
        """The exact shape asked for, for logging/debugging."""
        return {
            "user_query": self.user_query,
            "steps": [vars(record) for record in self.steps],
            "tool_results": self.tool_results,
            "retrieval_attempts": self.retrieval_attempts,
            "tool_calls": self.tool_calls,
            "errors": self.errors,
            "elapsed_time": round(self.elapsed_time, 2),
            "previous_actions": self.previous_actions,
            "total_tokens": self.total_tokens,
        }
