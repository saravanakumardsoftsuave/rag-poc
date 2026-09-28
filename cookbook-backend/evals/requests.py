"""The 10 shared recipe-adaptation requests raced against both systems (W7
requirement 3). Grounded in the two ingested cookbooks' real recipes. At
least 3 (R3, R6, R10) are cascading: the ingredient's first-choice substitute
(under just its own allergen tag) itself carries a different tag that the
full request also excludes, forcing a second substitute_ingredient call.
"""

from dataclasses import dataclass, field


@dataclass
class RaceRequest:
    id: str
    recipe_query: str
    requested_servings: int
    exclude_allergens: list[str]
    diet: str = "none"
    cascading: bool = False
    notes: str = ""


REQUESTS: list[RaceRequest] = [
    RaceRequest("R1", "Sambar", 8, [], cascading=False,
                notes="Pure scale, no allergens excluded - control case, no substitution tool needed."),
    RaceRequest("R2", "Paneer Butter Masala", 6, ["dairy"], cascading=False,
                notes="Single-allergen exclusion: paneer/cream/butter each resolve in one substitute_ingredient call."),
    RaceRequest("R3", "Paneer Butter Masala", 10, ["dairy", "tree_nut"], cascading=True,
                notes="cream's and butter's first-choice substitutes are themselves tree_nut - needs a second pass."),
    RaceRequest("R4", "Gulab Jamun", 12, ["dairy"], cascading=False,
                notes="khoya and milk both resolve in one pass each; no collision."),
    RaceRequest("R5", "Gulab Jamun", 8, ["dairy", "gluten"], cascading=False,
                notes="Multi-allergen exclusion, but flour's substitute (besan) isn't dairy/gluten either - "
                      "shows not every multi-allergen request cascades."),
    RaceRequest("R6", "Dal Makhani", 8, ["dairy", "tree_nut"], cascading=True,
                notes="Same cascade pattern as R3 (cream, butter) in a different recipe."),
    RaceRequest("R7", "Dal Makhani", 6, ["dairy"], cascading=False,
                notes="Single-allergen exclusion, no cascade."),
    RaceRequest("R8", "Dal Makhani", 6, ["dairy", "peanut"], cascading=False,
                notes="peanut isn't present in this recipe at all - tests no invented substitution."),
    RaceRequest("R9", "Masala Dosa", 10, ["gluten", "dairy"], cascading=False,
                notes="Batter is rice + urad dal (already gluten-free); tests the system doesn't over-substitute."),
    RaceRequest("R10", "Paneer Butter Masala", 3, ["dairy", "tree_nut", "gluten"], cascading=True,
                notes="Same cascade as R3 plus a decoy allergen (gluten, absent) and a downscale."),
]
