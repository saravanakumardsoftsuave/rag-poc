"""Safety limits for the agent loop.

Deliberately no cost/dollar-budget limit - explicitly asked against earlier
in this project and reconfirmed when a later request proposed reversing
that. Steps, calls, attempts, errors, tokens and wall-clock time are all
bounded; a benchmark may still *report* a cost figure, but nothing here
stops the loop on cost.
"""

from app.agent.state import AgentState

MAX_STEPS = 10
MAX_TOOL_CALLS = 10
MAX_RETRIEVAL_ATTEMPTS = 3
MAX_ERRORS = 3
MAX_EXECUTION_TIME = 60  # seconds
MAX_TOKENS = 2000  # total prompt+completion tokens across every LLM call in one request


def check_safety_limits(state: AgentState) -> str | None:
    """Return the name of the first breached limit, or None if the agent may
    continue. Checked once at the top of every loop iteration, before the
    next action runs."""
    if len(state.steps) >= MAX_STEPS:
        return "max_steps"
    if state.tool_calls >= MAX_TOOL_CALLS:
        return "max_tool_calls"
    if state.retrieval_attempts >= MAX_RETRIEVAL_ATTEMPTS:
        return "max_retrieval_attempts"
    if state.errors >= MAX_ERRORS:
        return "max_errors"
    if state.elapsed_time >= MAX_EXECUTION_TIME:
        return "max_execution_time"
    if state.total_tokens >= MAX_TOKENS:
        return "max_tokens"
    return None


def stable_arguments_key(arguments: dict) -> str:
    """A stable, order-independent string for one call's arguments, so the
    same call with the same arguments always produces the same signature."""
    return str(sorted(arguments.items()))


def is_repeated_action(state: AgentState, tool: str, arguments: dict) -> bool:
    """True if this exact (tool, arguments) pair already ran - the agent is
    stuck repeating itself, not making progress, e.g.:

        search_knowledge_base("cardamom")
        search_knowledge_base("cardamom")
    """
    signature = (tool, stable_arguments_key(arguments))
    return signature in state.previous_actions
