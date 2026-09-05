"""A fixed, non-agentic pipeline: same model, same tools, same output shape
as run_agent() (see agent.py) - but every step is hardcoded instead of an
LLM deciding what to do next. Exists only to benchmark against the agent
(see benchmark.py): does answering these questions actually need a decision
loop, or does a fixed sequence of steps get the same results for less cost?

Because every step here is a fixed rule, this pipeline can only chain step 2
into step 3 when the substitution/allergen target is *named in the
question itself* - it has no way to read step 2's search result and decide
what "it" or "that ingredient" refers to. That's not a bug to fix; it's the
actual limitation a fixed pipeline has that an agent doesn't, and is exactly
what the benchmark is designed to surface.
"""

import logging
import re

from app.agent.tools import Diet, TOOLS_BY_NAME
from app.config import settings
from app.rag import count_tokens, generate_answer

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_ANSWER = (
    "I couldn't find sufficient evidence in the available knowledge base to "
    "answer this question."
)

FINAL_ANSWER_PROMPT = (
    "Answer the user's question using only the information returned by the "
    "tools below. Never invent details the tools did not return. If the "
    "tools didn't actually return enough to answer, say so plainly.\n\n"
    "Question: {question}\n\n"
    "Tool results:\n{results}\n\n"
    "Answer:"
)

_DIET_VALUES = [diet.value for diet in Diet]
_SUBSTITUTION_RE = re.compile(
    r"(?:substitute|alternative|replacement)s?\s+for\s+([a-zA-Z ]+?)(?:[.?!]|$)",
    re.IGNORECASE,
)
_ALLERGEN_TRIGGER_RE = re.compile(r"\ballerg", re.IGNORECASE)
_ALLERGEN_INGREDIENT_RE = re.compile(
    r"\ballergens?\s+(?:in|of)\s+([a-zA-Z ]+?)(?:[.?!]|$)",
    re.IGNORECASE,
)


def _detect_diet(question: str) -> str | None:
    lowered = question.lower()
    return next((diet for diet in _DIET_VALUES if diet in lowered), None)


def _fixed_step_2(question: str) -> tuple[str, str] | None:
    """The hardcoded rule for whether/which tool to call after search.
    Only fires when the target ingredient is spelled out in the question."""
    diet = _detect_diet(question)
    if diet:
        match = _SUBSTITUTION_RE.search(question)
        if match:
            return "substitute_ingredient", f"{match.group(1).strip()}, {diet}"
        return None
    if _ALLERGEN_TRIGGER_RE.search(question):
        match = _ALLERGEN_INGREDIENT_RE.search(question)
        if match:
            return "get_allergen_profile", match.group(1).strip()
    return None


def run_workflow(question: str) -> dict:
    """Step 1: always search. Step 2: a fixed regex rule, not an LLM,
    decides whether to also call substitute_ingredient/get_allergen_profile.
    Step 3: answer from whatever was found - same prompt, same model as the
    agent's _finalize_answer."""
    tool_results = []

    logger.info("[WORKFLOW] Step 1: search_knowledge_base")
    search_result = TOOLS_BY_NAME["search_knowledge_base"].invoke(question)
    tool_results.append({"tool": "search_knowledge_base", "arguments": {"query": question}, "result": search_result})
    best_score = search_result.get("best_relevance_score", 0.0)
    logger.info("[WORKFLOW] Evidence sufficient: %s", best_score >= settings.relevance_score_cutoff)

    if best_score < settings.relevance_score_cutoff:
        logger.info("[WORKFLOW] Stopping: insufficient_evidence")
        return {
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "sources": [],
            "stop_reason": "insufficient_evidence",
            "total_tokens": 0,
            "tool_calls": 1,
            "steps": 1,
        }

    step_2 = _fixed_step_2(question)
    if step_2:
        tool_name, argument = step_2
        logger.info("[WORKFLOW] Step 2 (fixed rule matched): %s(%s)", tool_name, argument)
        result = TOOLS_BY_NAME[tool_name].invoke(argument)
        tool_results.append({"tool": tool_name, "arguments": {"input": argument}, "result": result})
    else:
        logger.info("[WORKFLOW] Step 2: no fixed rule matched, skipping")

    results_text = "\n\n".join(f"{entry['tool']}({entry['arguments']}) ->\n{entry['result']}" for entry in tool_results)
    prompt = FINAL_ANSWER_PROMPT.format(question=question, results=results_text)
    answer = generate_answer(prompt)
    total_tokens = count_tokens(prompt) + count_tokens(answer)
    sources = sorted({chunk["source"] for chunk in search_result.get("chunks", []) if chunk.get("source")})
    logger.info("[WORKFLOW] Stopping: goal_completed")
    return {
        "answer": answer,
        "sources": sources,
        "stop_reason": "goal_completed",
        "total_tokens": total_tokens,
        "tool_calls": len(tool_results),
        "steps": len(tool_results),
    }
