# Docstring-as-prompt + recoverable error rewrite (W9 requirement 5)

Tool: `get_nutrition` on **our own** server (`recipe_server.py` / `app/agent/tools/recipe_tools.py`).
Same failing call in both versions: `get_nutrition("cashew")` (the table's real key is `cashews`, plural).

## Before

```python
def get_nutrition(ingredient: str) -> dict:
    """Get nutrition for ingredient."""
    entry = NUTRITION_TABLE.get(ingredient)
    if entry is None:
        return {"error": "not found"}
    return entry
```

Call: `get_nutrition("cashew")` -> `{"error": "not found"}`

The docstring states only WHAT the tool does, not how a caller should use it or
recover from a miss, and the not-found path is a bare, information-free error -
the model has no way to tell a spelling miss from a dead lookup, and nothing in
the response points it toward the ingredient name that would actually work.

## After (current implementation)

```python
def get_nutrition(ingredient: str) -> dict:
    """Looks up per-100g calories, macros, and allergen tags for one named
    ingredient already in the nutrition table. Does not search recipes and
    does not propose a substitute - call substitute_ingredient for that."""
    entry = get_ingredient(ingredient)
    if entry is not None:
        return {"ingredient": ingredient, "found": True, "matched_name": resolve_ingredient_key(ingredient), **entry,
                "suggestion": None, "message": None}
    suggestions = find_similar(ingredient)
    suggestion = suggestions[0] if suggestions else None
    message = (f"no ingredient matched '{ingredient}': try '{suggestion}'" if suggestion
               else f"no ingredient matched '{ingredient}' and no close match was found")
    return {"ingredient": ingredient, "found": False, ..., "suggestion": suggestion, "message": message}
```

Call: `get_nutrition("cashew")` -> (actual output, captured live this session)
```json
{
  "ingredient": "cashew",
  "found": false,
  "matched_name": null,
  "calories_kcal_per_100g": null,
  "protein_g": null,
  "carbs_g": null,
  "fat_g": null,
  "allergen_tags": [],
  "suggestion": "cashews",
  "message": "no ingredient matched 'cashew': try 'cashews'"
}
```

The docstring now also states what the tool does NOT do (steering the model to
the right tool for substitution instead of assuming this one does everything),
and the not-found path carries a `difflib`-based `suggestion` plus a plain-English
`message` naming the exact term that would work.

## Transcript: how the model handles the same failing call

**Before** (bare `{"error": "not found"}`): with no signal about what went
wrong or what to try instead, the model has two failure modes it can't tell
apart from this response alone - treat "cashew" as genuinely absent from the
table (and either give up or, worse, invent nutrition numbers for it), or
retry with an arbitrary guess. Nothing in the response narrows that down.

**After** (`suggestion`/`message` populated): the same call now hands the
model the literal corrected term. In the turn transcript format this loop
uses (`TOOL: get_nutrition ARGS: {"ingredient": "cashew"} -> RESULT: {...}`),
the very next line in the "Actions so far" block the model reads on its next
turn contains `"suggestion": "cashews"` and the plain-English message - a
model that reads its own tool results (as this loop's prompt requires every
turn) has the fix stated directly in front of it rather than needing to
infer one, which is the concrete difference this rewrite makes.
