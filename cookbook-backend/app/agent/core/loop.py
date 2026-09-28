"""The agentic loop. Deliberately knows only about ToolRegistry/Tool (see
registry.py) - never about MCP, never about any specific tool module. This is
what lets adding a second MCP server be a config-only change: this file does
not change no matter where the registry's tools came from.

The local generation model (Qwen2.5-1.5B-Instruct via transformers.pipeline)
has no native function-calling, so tool selection uses a plain one-line
convention (TOOL: name ARGS: {...} / FINAL: {...}) parsed defensively. A
malformed or unknown-tool reply ends the request as a clean failure, never an
exception - this shows up as a real (non-zero) failure rate for the agent
system in the W7 race, which is expected and reported honestly rather than
hidden.
"""

import json
import logging
import re

from app.agent.core.budgets import Budgets, BudgetExceeded, BudgetTracker
from app.agent.core.registry import ToolRegistry
from app.rag import generate_answer, get_generator

logger = logging.getLogger(__name__)

_TOOL_PATTERN = re.compile(
    r"TOOL[:\s]*[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_]*)[\"']?[,\s]*ARGS[:\s]*(?P<rest>.*)",
    re.IGNORECASE | re.DOTALL,
)
_FINAL_PATTERN = re.compile(r"FINAL[:\s]*(?P<rest>.*)", re.IGNORECASE | re.DOTALL)
_KV_PATTERN = re.compile(r'(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*"(?P<val>[^"]*)"')


def _loose_tool_call(raw: str, registry: ToolRegistry) -> tuple[str, dict] | None:
    """Last-resort fallback for small-model quirks where the reply names a
    real tool but doesn't follow the TOOL:/ARGS: convention (e.g.
    'CALCULATOR_TOOL question: "12 * 4"'). Looks for a known tool name near
    the start of the reply and pulls out any quoted key: "value" pairs as
    its arguments."""
    head = raw[:80].upper().replace("_", "").replace(" ", "")
    for tool in registry.tools:
        if tool.name.upper().replace("_", "") in head:
            args = {m.group("key"): m.group("val") for m in _KV_PATTERN.finditer(raw)}
            return tool.name, args
    return None


def _count_tokens(text: str) -> int:
    return len(get_generator().tokenizer(text)["input_ids"])


def _extract_first_json(text: str) -> dict | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _build_turn_prompt(question: str, registry: ToolRegistry, transcript: list[str]) -> str:
    tools_block = registry.as_prompt_block()
    transcript_block = "\n".join(transcript) if transcript else "(none yet)"
    return (
        "You are a tool-calling agent for a cookbook assistant. Solve the request by "
        "calling tools one at a time; once you have enough information, give a final "
        "answer.\n\n"
        f"Available tools:\n{tools_block}\n\n"
        f"Request: {question}\n\n"
        f"Actions so far:\n{transcript_block}\n\n"
        "Reply with exactly one line, either:\n"
        'TOOL: <tool_name> ARGS: <json object of arguments>\n'
        "or:\n"
        'FINAL: <json object with keys "answer" and "sources">\n'
        "No other text, no explanation."
    )


async def run_agentic_loop(
    question: str,
    registry: ToolRegistry,
    budgets: Budgets | None = None,
    request_id: str = "",
) -> dict:
    budgets = budgets or Budgets()
    tracker = BudgetTracker(budgets, request_id=request_id)
    transcript: list[str] = []
    tool_calls: list[dict] = []
    last_result: dict | None = None

    while True:
        try:
            tracker.check()
        except BudgetExceeded as exc:
            tracker.log_exceeded(exc.budget)
            return {
                "status": "budget_exceeded",
                "budget": exc.budget,
                "partial_result": last_result,
                "tool_calls": tool_calls,
                "iterations_used": tracker.iterations,
                "tokens_used": tracker.tokens,
                "cost_usd": tracker.cost_usd,
                "elapsed_s": tracker.elapsed_s,
            }

        prompt = _build_turn_prompt(question, registry, transcript)
        tracker.add_tokens(_count_tokens(prompt))
        raw = generate_answer(prompt)
        tracker.add_tokens(_count_tokens(raw))

        final_match = _FINAL_PATTERN.search(raw)
        tool_match = _TOOL_PATTERN.search(raw)

        # Whichever directive appears first wins, since a malformed reply can
        # contain stray text before the real TOOL:/FINAL: line.
        if final_match and (not tool_match or final_match.start() <= tool_match.start()):
            parsed = _extract_first_json(final_match.group("rest"))
            if parsed is not None:
                return {
                    "status": "ok",
                    "answer": parsed.get("answer", ""),
                    "sources": parsed.get("sources", []),
                    "tool_calls": tool_calls,
                    "iterations_used": tracker.iterations,
                    "tokens_used": tracker.tokens,
                    "cost_usd": tracker.cost_usd,
                    "elapsed_s": tracker.elapsed_s,
                }
            logger.info("run_agentic_loop: unparseable FINAL reply %r", raw)
            return _failure("unparseable_final", tracker, raw, tool_calls)

        call = None
        if tool_match:
            name = tool_match.group("name")
            args = _extract_first_json(tool_match.group("rest")) or {}
            tool = registry.get(name)
            if tool is None:
                logger.info("run_agentic_loop: unknown tool %r requested", name)
                return _failure("unknown_tool", tracker, raw, tool_calls)
            call = (name, args, tool)
        else:
            loose = _loose_tool_call(raw, registry)
            if loose is not None:
                loose_name, loose_args = loose
                call = (loose_name, loose_args, registry.get(loose_name))

        if call is not None:
            name, args, tool = call
            try:
                result = await tool.call(args)
            except TypeError as exc:
                logger.info("run_agentic_loop: bad args for tool %r: %s", name, exc)
                return _failure("bad_tool_args", tracker, raw, tool_calls)
            tool_calls.append({"name": name, "args": args, "result": result})
            terminal = _as_terminal_result(result, tracker, tool_calls)
            if terminal is not None:
                return terminal
            last_result = result
            transcript.append(f"TOOL: {name} ARGS: {json.dumps(args)} -> RESULT: {json.dumps(result)}")
            continue

        logger.info("run_agentic_loop: unparseable reply %r", raw)
        return _failure("unparseable_reply", tracker, raw, tool_calls)


def _as_terminal_result(result: dict, tracker: BudgetTracker, tool_calls: list[dict]) -> dict | None:
    """Some tools (rag_tool, calculator_tool, general_tool) already return a
    complete {"answer","sources"} shape - that IS the final answer, so the
    loop returns immediately instead of spending another turn asking the
    model to restate what it was just given. Tools with a different shape
    (search_recipes, get_nutrition, substitute_ingredient) are intermediate
    data and fall through to a normal next turn."""
    if isinstance(result, dict) and "answer" in result and "sources" in result:
        return {
            "status": "ok",
            "answer": result["answer"],
            "sources": result["sources"],
            "tool_calls": tool_calls,
            "iterations_used": tracker.iterations,
            "tokens_used": tracker.tokens,
            "cost_usd": tracker.cost_usd,
            "elapsed_s": tracker.elapsed_s,
        }
    return None


def _failure(reason: str, tracker: BudgetTracker, raw: str, tool_calls: list[dict]) -> dict:
    return {
        "status": "failed",
        "reason": reason,
        "raw": raw,
        "tool_calls": tool_calls,
        "iterations_used": tracker.iterations,
        "tokens_used": tracker.tokens,
        "cost_usd": tracker.cost_usd,
        "elapsed_s": tracker.elapsed_s,
    }
