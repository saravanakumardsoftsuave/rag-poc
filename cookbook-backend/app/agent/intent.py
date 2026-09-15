"""Shared, deterministic question-intent detection - no LLM involved.

Used two places: workflow.py's fixed step-2 rule (a regex decides whether to
call substitute_ingredient/get_allergen_profile at all) and agent.py's
grounding guard (forces the agent to call the matching tool before it's
allowed to answer a substitution/allergen question from its own pretrained
knowledge instead of the fixed tables in tools.py - see agent.py's
_forced_grounding_call and evals/trajectory_eval.py's "bypass_probe" case).

Ingredient extraction matches against the tables' own keys rather than
parsing free-text phrasing ("substitute for X", "instead of X", "swap X"...)
because the tables are the fixed vocabulary that actually matters here - a
question can name an ingredient in any phrasing and this still finds it.
"""

import re

from app.agent.tools import ALLERGEN_PROFILES, SUBSTITUTIONS, Diet

_DIET_VALUES = [diet.value for diet in Diet]
_ALLERGEN_TRIGGER_RE = re.compile(r"\ballerg", re.IGNORECASE)

_SUBSTITUTION_VOCABULARY = sorted({ingredient for ingredient, _ in SUBSTITUTIONS}, key=len, reverse=True)
_ALLERGEN_VOCABULARY = sorted(ALLERGEN_PROFILES.keys(), key=len, reverse=True)


def detect_diet(question: str) -> str | None:
    """The first Diet value named in the question, or None."""
    lowered = question.lower()
    return next((diet for diet in _DIET_VALUES if diet in lowered), None)


def mentions_allergen_intent(question: str) -> bool:
    return bool(_ALLERGEN_TRIGGER_RE.search(question))


def _earliest_match(question: str, vocabulary: list[str]) -> str | None:
    """The vocabulary entry that appears earliest in the question - not just
    the first one checked - so "Paneer Butter Masala" resolves to "paneer"
    (it's named first) rather than whichever table key happens to sort
    first. Ties (same position) fall back to the longer entry, since
    `vocabulary` is pre-sorted longest-first and this is a stable search."""
    lowered = question.lower()
    best: tuple[int, str] | None = None
    for ingredient in vocabulary:
        index = lowered.find(ingredient)
        if index == -1:
            continue
        if best is None or index < best[0]:
            best = (index, ingredient)
    return best[1] if best else None


def detect_substitution_target(question: str) -> str | None:
    """The earliest-named ingredient in `question` that has a known
    substitution-table entry, or None if no such ingredient is named."""
    return _earliest_match(question, _SUBSTITUTION_VOCABULARY)


def detect_allergen_target(question: str) -> str | None:
    """The earliest-named ingredient in `question` that has a known
    allergen-table entry, or None if no such ingredient is named."""
    return _earliest_match(question, _ALLERGEN_VOCABULARY)
