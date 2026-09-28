"""MCP server two: simulates a third-party ingredient database (W9). Looks up
one ingredient by name and returns allergen flags plus per-100g nutrition.
No LLM call anywhere in this file, and no import from app/agent/ - this file
plays the part of code someone else wrote and shipped as a binary/package,
not something we authored as part of our own agent.
"""

from mcp.server.fastmcp import FastMCP

from app.mcp_servers.ingredient_db_data import lookup

mcp = FastMCP("ingredient-server")


@mcp.tool()
def lookup_ingredient(name: str) -> dict:
    """Looks up allergen flags and per-100g nutrition for one named ingredient
    in the third-party ingredient database. If no exact match, returns a
    suggestion for the closest known ingredient name instead of a bare error."""
    result = lookup(name)
    if not result["found"] and result["suggestion"]:
        result["message"] = f"no ingredient matched '{name}': try '{result['suggestion']}'"
    elif not result["found"]:
        result["message"] = f"no ingredient matched '{name}' and no close match was found"
    else:
        result["message"] = None
    return result


if __name__ == "__main__":
    mcp.run()
