# Tool count before -> after (W9 requirement 3)

Captured from a real `session.list_tools()` call via `app/agent/core/mcp_adapter.py`
against `config/mcp_servers.json`, not from notes.

**Before** (server one only - `recipe`): **6 tools**
`rag_tool`, `calculator_tool`, `general_tool`, `search_recipes`, `get_nutrition`, `substitute_ingredient`

**After** (server one + two - `recipe` + `ingredient`): **7 tools**
`rag_tool`, `calculator_tool`, `general_tool`, `search_recipes`, `get_nutrition`, `substitute_ingredient`, `lookup_ingredient`

The new tool, `lookup_ingredient`, comes entirely from `ingredient_server.py` (server two) -
discovered dynamically, not registered anywhere in `app/agent/` (see `agent_diff.txt`).
