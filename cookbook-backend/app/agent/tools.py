"""The three tools the agent can call.

Each is a plain function plus a name/description pair used to build the
controller's prompt (see agent.py's DECIDE_PROMPT) and to dispatch on. No
framework wrapper - a single-string-argument tool doesn't need one.

Each tool wraps existing, already-deterministic data - it does not
reimplement retrieval, and it does not let the LLM invent a substitution.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from app.agent.prompt_injection import sanitize_chunk_text
from app.retrieval import hybrid_search


class Diet(str, Enum):
    """The only diet values substitute_ingredient understands - a free-text
    diet string can't be checked against the substitution table's keys, an
    enum can."""

    VEGAN = "vegan"
    DAIRY_FREE = "dairy-free"
    GLUTEN_FREE = "gluten-free"
    DIABETIC_FRIENDLY = "diabetic-friendly"


class Allergen(str, Enum):
    """The only allergen values get_allergen_profile returns."""

    DAIRY = "dairy"
    GLUTEN = "gluten"
    NUTS = "nuts"
    SOY = "soy"
    EGG = "egg"
    SESAME = "sesame"


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[[str], dict]

    def invoke(self, argument: str) -> dict:
        return self.func(argument)


def _search_knowledge_base(query: str) -> dict:
    """Vector search + BM25 search, fused with RRF, then reordered by a
    cross-encoder reranker. Returns the top relevant chunks and the best
    relevance score found among them."""
    matches, best_score = hybrid_search(query)
    return {
        "chunks": [
            {
                "id": match.get("id"),
                "source": match["source"],
                # Bonus challenge (evals/prompt_injection/): a chunk is
                # third-party document content, not a trusted instruction
                # source - strip anything instruction-shaped before it can
                # reach the final-answer prompt.
                "text": sanitize_chunk_text(match["text"]),
            }
            for match in matches
        ],
        "best_relevance_score": best_score,
    }


# A fixed substitution table, not an LLM guess - if a pair isn't in here,
# the tool says so instead of inventing a plausible-sounding swap. Keys are
# lowercased (ingredient, diet) pairs.
SUBSTITUTIONS: dict[tuple[str, str], str] = {
    ("butter", "vegan"): "margarine or coconut oil",
    ("butter", "dairy-free"): "margarine or coconut oil",
    ("ghee", "vegan"): "vegan butter or coconut oil",
    ("milk", "vegan"): "soy milk, almond milk, or oat milk",
    ("milk", "dairy-free"): "soy milk, almond milk, or oat milk",
    ("cream", "vegan"): "coconut cream or cashew cream",
    ("cream", "dairy-free"): "coconut cream or cashew cream",
    ("paneer", "vegan"): "firm tofu",
    ("yogurt", "vegan"): "coconut yogurt or soy yogurt",
    ("egg", "vegan"): "1 tbsp ground flaxseed + 3 tbsp water (per egg), or mashed banana",
    ("honey", "vegan"): "maple syrup or agave syrup",
    ("wheat flour", "gluten-free"): "a 1:1 gluten-free flour blend",
    ("all-purpose flour", "gluten-free"): "a 1:1 gluten-free flour blend",
    ("sugar", "diabetic-friendly"): "stevia or another low-glycemic sweetener",
}


def _substitute_ingredient(argument: str) -> dict:
    """Look up a diet-appropriate substitute for one ingredient in a fixed
    table. Argument format: "<ingredient>, <diet>", e.g. "butter, vegan" -
    `diet` must be one of the Diet enum values."""
    ingredient, _, diet_text = argument.partition(",")
    ingredient = ingredient.strip().lower()
    diet_text = diet_text.strip().lower()
    if not ingredient or not diet_text:
        return {"error": f"Expected \"ingredient, diet\", got {argument!r}."}
    try:
        diet = Diet(diet_text)
    except ValueError:
        valid = ", ".join(d.value for d in Diet)
        return {"error": f"Unknown diet {diet_text!r}. Valid diets: {valid}."}
    substitute = SUBSTITUTIONS.get((ingredient, diet.value))
    if substitute is None:
        return {"error": f"No known substitute for {ingredient!r} under a {diet.value!r} diet."}
    return {"ingredient": ingredient, "diet": diet.value, "substitute": substitute}


# A fixed allergen table, not an LLM guess. An ingredient missing from this
# table is NOT the same as "allergen-free" - it means we have no data on
# file, and the tool says so explicitly rather than implying safety.
ALLERGEN_PROFILES: dict[str, list[Allergen]] = {
    "butter": [Allergen.DAIRY],
    "ghee": [Allergen.DAIRY],
    "milk": [Allergen.DAIRY],
    "cream": [Allergen.DAIRY],
    "paneer": [Allergen.DAIRY],
    "yogurt": [Allergen.DAIRY],
    "wheat flour": [Allergen.GLUTEN],
    "all-purpose flour": [Allergen.GLUTEN],
    "cashews": [Allergen.NUTS],
    "cashew": [Allergen.NUTS],
    "almonds": [Allergen.NUTS],
    "peanuts": [Allergen.NUTS],
    "soy milk": [Allergen.SOY],
    "soy sauce": [Allergen.SOY],
    "egg": [Allergen.EGG],
    "sesame": [Allergen.SESAME],
    "tahini": [Allergen.SESAME],
}


def _get_allergen_profile(ingredient: str) -> dict:
    """Look up known allergens for one ingredient in a fixed table. An
    ingredient not on file is reported as "unverified", never as
    "allergen-free" - the tool must not imply a safety guarantee it can't
    back up."""
    key = ingredient.strip().lower()
    if not key:
        return {"error": "Expected an ingredient name."}
    allergens = ALLERGEN_PROFILES.get(key)
    if allergens is None:
        return {
            "ingredient": key,
            "allergens": [],
            "note": "No allergen data on file for this ingredient - this is not a claim that it's allergen-free.",
        }
    return {"ingredient": key, "allergens": [allergen.value for allergen in allergens]}


TOOLS = [
    Tool(
        name="search_knowledge_base",
        description=(
            "Search the cookbook knowledge base for passages relevant to a "
            "query. Runs vector search + BM25, fused with RRF, then "
            "cross-encoder reranked. Argument: the search query."
        ),
        func=_search_knowledge_base,
    ),
    Tool(
        name="substitute_ingredient",
        description=(
            "Look up a diet-appropriate substitute for exactly one "
            "ingredient - nothing else. Argument: \"<ingredient>, <diet>\", "
            "e.g. \"butter, vegan\". diet must be one of: "
            + ", ".join(d.value for d in Diet)
            + "."
        ),
        func=_substitute_ingredient,
    ),
    Tool(
        name="get_allergen_profile",
        description=(
            "Look up known allergens for exactly one ingredient - nothing "
            "else. Argument: the ingredient name. Returns allergens from: "
            + ", ".join(a.value for a in Allergen)
            + "."
        ),
        func=_get_allergen_profile,
    ),
]
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
