"""The agent: an LLM controller that repeatedly decides which tool to call,
executes it, and updates state - until the goal is complete or a safety
limit stops it (see safety.py). Tools are defined in tools.py.
"""

import logging

from app.agent.safety import check_safety_limits, is_repeated_action, stable_arguments_key
from app.agent.state import AgentState
from app.agent.tools import TOOLS, TOOLS_BY_NAME
from app.config import settings
from app.rag import count_tokens, generate_answer, get_generator

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_ANSWER = (
    "I couldn't find sufficient evidence in the available knowledge base to "
    "answer this question."
)

DECIDE_PROMPT = (
    "You are an agent answering a user's question using a cookbook knowledge "
    "base and a fixed ingredient-substitution table. Decide the single next "
    "action.\n\n"
    "User question: {question}\n\n"
    "Actions taken so far:\n{history}\n\n"
    "Best relevance score found so far: {score:.2f} (need >= {cutoff:.2f} to answer)\n\n"
    "Available tools:\n{tool_list}\n\n"
    "Choose exactly one of:\n"
    "- a tool above, as `<tool name>: <argument>`\n"
    "- `answer` - enough evidence has been found; the final answer will be "
    "written from what the tools returned\n"
    "- `give_up` - further tool calls will not help\n\n"
    "Never invent information the tools did not return. Reply with only the "
    "chosen action, nothing else."
)

FINAL_ANSWER_PROMPT = (
    "Answer the user's question using only the information returned by the "
    "tools below. Never invent details the tools did not return. If the "
    "tools didn't actually return enough to answer, say so plainly.\n\n"
    "Question: {question}\n\n"
    "Tool results:\n{results}\n\n"
    "Answer:"
)


def _plain_argument(arguments: dict) -> str:
    """The reverse of _display_arguments: render a labeled-argument dict back
    as the plain `tool: argument` text the model is asked to produce. Shown
    in _format_history so the example the model sees matches the format it's
    asked to reply in - showing it a dict repr here made a small model copy
    that (wrong) format back, instead of the requested one."""
    if "ingredient" in arguments and "diet" in arguments:
        return f"{arguments['ingredient']}, {arguments['diet']}"
    if "ingredient" in arguments:
        return arguments["ingredient"]
    return arguments.get("query", str(arguments))


def _format_history(state: AgentState) -> str:
    if not state.steps:
        return "(none yet)"
    lines = []
    for record in state.steps:
        preview = str(record.result)
        if len(preview) > 200:
            preview = preview[:200] + "..."
        lines.append(f"{record.step}. {record.tool}: {_plain_argument(record.arguments)} -> {preview}")
    return "\n".join(lines)


def _decide_next_action(state: AgentState) -> tuple[str, str]:
    """Ask the LLM which tool to call next, or whether to answer/give up."""
    prompt = DECIDE_PROMPT.format(
        question=state.user_query,
        history=_format_history(state),
        score=state.best_relevance_score,
        cutoff=settings.relevance_score_cutoff,
        tool_list="\n".join(f"- {t.name}: {t.description}" for t in TOOLS),
    )
    output = get_generator()(
        [{"role": "user", "content": prompt}],
        max_new_tokens=64,
        do_sample=False,
    )
    text = output[0]["generated_text"][-1]["content"].strip()
    state.total_tokens += count_tokens(prompt) + count_tokens(text)
    name, _, argument = text.partition(":")
    name = name.strip().lower()
    argument = argument.strip().strip('"')

    if name in TOOLS_BY_NAME and argument:
        return name, argument
    if name in ("answer", "give_up"):
        return name, ""

    # Unparseable reply. Retrying search_knowledge_base with the *original*
    # question here was the earlier bug: that query is always already in
    # tried_queries (it's literally the first thing the agent ever searched),
    # so it triggered is_repeated_action on the very next iteration - every
    # single request ended in the same repeated_action fallback, regardless
    # of whether good evidence had already been found. Falling through to
    # "answer" when the evidence bar is already met (or "give_up" otherwise)
    # doesn't have that failure mode.
    logger.warning("[AGENT] Unusable action %r", text)
    if state.best_relevance_score >= settings.relevance_score_cutoff:
        return "answer", ""
    return "give_up", ""


def _display_arguments(tool_name: str, argument: str) -> dict:
    """Turn a tool's single raw string argument into a labeled dict for logs
    and AgentState.steps. substitute_ingredient's argument is a
    comma-separated pair, so it gets split into two named fields."""
    if tool_name == "substitute_ingredient":
        ingredient, _, diet = argument.partition(",")
        return {"ingredient": ingredient.strip(), "diet": diet.strip()}
    if tool_name == "get_allergen_profile":
        return {"ingredient": argument.strip()}
    return {"query": argument}


def _execute_tool(state: AgentState, tool_name: str, argument: str) -> None:
    arguments = _display_arguments(tool_name, argument)
    logger.info("[AGENT] Selected tool: %s", tool_name)
    logger.info("[AGENT] Arguments: %s", arguments)

    if is_repeated_action(state, tool_name, arguments):
        logger.info(
            "[AGENT] Repeated action detected: %s%s already ran; the agent is stuck",
            tool_name,
            arguments,
        )
        state.stop_reason = "repeated_action"
        return

    state.previous_actions.append((tool_name, stable_arguments_key(arguments)))
    state.tool_calls += 1
    if tool_name == "search_knowledge_base":
        state.retrieval_attempts += 1

    logger.info("[TOOL] Executing %s...", tool_name)
    try:
        result = TOOLS_BY_NAME[tool_name].invoke(argument)
    except Exception as exc:
        logger.exception("[TOOL] %s failed", tool_name)
        state.errors += 1
        result = {"error": str(exc)}

    if tool_name == "search_knowledge_base" and isinstance(result, dict):
        chunks = result.get("chunks", [])
        logger.info("[TOOL] Results returned: %d", len(chunks))
        for chunk in chunks:
            state.chunks[chunk.get("id") or chunk["text"]] = chunk
        state.best_relevance_score = max(state.best_relevance_score, result.get("best_relevance_score", 0.0))

    state.record_step(tool_name, arguments, result)


def _insufficient_evidence(state: AgentState, stop_reason: str) -> dict:
    logger.info("[AGENT] Stopping: %s", stop_reason)
    return {
        "answer": INSUFFICIENT_EVIDENCE_ANSWER,
        "sources": [],
        "stop_reason": stop_reason,
        "total_tokens": state.total_tokens,
        "tool_calls": state.tool_calls,
        "steps": len(state.steps),
    }


def _summarize_tool_result(entry: dict) -> str:
    """The result text actually put in the final-answer prompt. search's raw
    result repeats an id/source key per chunk on top of the chunk text
    itself - real prompt bloat for no benefit here - so only the chunk text
    goes in; other tools' results are already small enough to pass through."""
    if entry["tool"] == "search_knowledge_base" and isinstance(entry["result"], dict):
        chunks = entry["result"].get("chunks", [])
        return "\n\n".join(chunk["text"] for chunk in chunks if chunk.get("text"))
    return str(entry["result"])


def _finalize_answer(state: AgentState) -> dict:
    logger.info("[AGENT] Evidence sufficient: True - generating final answer")
    results = "\n\n".join(
        f"{entry['tool']}({entry['arguments']}) ->\n{_summarize_tool_result(entry)}" for entry in state.tool_results
    )
    prompt = FINAL_ANSWER_PROMPT.format(question=state.user_query, results=results)
    answer = generate_answer(prompt)
    state.total_tokens += count_tokens(prompt) + count_tokens(answer)
    sources = sorted({chunk["source"] for chunk in state.chunks.values() if chunk.get("source")})
    logger.info("[AGENT] Stopping: goal_completed")
    return {
        "answer": answer,
        "sources": sources,
        "stop_reason": "goal_completed",
        "total_tokens": state.total_tokens,
        "tool_calls": state.tool_calls,
        "steps": len(state.steps),
    }


def run_agent(question: str) -> dict:
    """Understand the goal, decide/select/execute tools, observe results,
    update state, and repeat until the goal is complete or a safety limit
    ends the attempt. Never generates an answer except through
    _finalize_answer, which only runs once the relevance cutoff is met."""
    state = AgentState(user_query=question)
    action, argument = "search_knowledge_base", question  # first move is always to search

    while True:
        stop_reason = check_safety_limits(state)
        if stop_reason:
            return _insufficient_evidence(state, stop_reason)

        logger.info("[AGENT] Step %d", len(state.steps) + 1)

        if action == "answer":
            logger.info("[AGENT] Evaluating whether to answer now...")
            if state.best_relevance_score >= settings.relevance_score_cutoff:
                return _finalize_answer(state)
            logger.info("[AGENT] Evidence sufficient: False - answer requested too early")
            return _insufficient_evidence(state, "insufficient_evidence")

        if action == "give_up":
            return _insufficient_evidence(state, "give_up")

        _execute_tool(state, action, argument)
        if state.stop_reason == "repeated_action" and state.best_relevance_score >= settings.relevance_score_cutoff:
            # The model re-issued a call it already made instead of picking
            # "answer" - a real, observed failure mode for this model size.
            # That's not being stuck: evidence is already sufficient, so take
            # the win instead of reporting insufficient evidence.
            logger.info("[AGENT] Repeated action, but evidence is already sufficient - answering instead of stopping")
            state.stop_reason = None
            return _finalize_answer(state)
        if state.stop_reason:
            return _insufficient_evidence(state, state.stop_reason)

        sufficient = state.best_relevance_score >= settings.relevance_score_cutoff
        logger.info("[AGENT] Evaluating %s result...", action)
        logger.info("[AGENT] Evidence sufficient: %s", sufficient)

        logger.info("[AGENT] Selecting next action...")
        try:
            action, argument = _decide_next_action(state)
        except Exception:
            logger.exception("[AGENT] Failed to decide the next action")
            state.errors += 1
            action, argument = "give_up", ""
