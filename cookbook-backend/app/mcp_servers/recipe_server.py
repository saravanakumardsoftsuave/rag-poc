"""MCP server one: exposes this app's own tools (rag/calculator/general chat
tools plus the three W7 recipe-adaptation tools) over stdio. No LLM call
happens anywhere in this file - the model only ever runs in the host process
(app/agent/core/loop.py). This server just exposes capabilities; the host
runs the model, per the W9 spec's own explicit warning against getting that
backwards.
"""

from mcp.server.fastmcp import FastMCP

from app.agent.tools.chat_tools import calculator_tool, general_tool, rag_tool
from app.agent.tools.recipe_tools import get_nutrition, search_recipes, substitute_ingredient

mcp = FastMCP("recipe-server")

mcp.tool()(rag_tool)
mcp.tool()(calculator_tool)
mcp.tool()(general_tool)
mcp.tool()(search_recipes)
mcp.tool()(get_nutrition)
mcp.tool()(substitute_ingredient)

if __name__ == "__main__":
    mcp.run()
