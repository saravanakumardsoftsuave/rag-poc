"""Builds a ToolRegistry (see registry.py) from a real MCP tools/list call
against every server listed in config/mcp_servers.json. This is the ONLY
place that knows about MCP - loop.py never imports this module directly (the
caller wires the two together), which is what makes adding a second server a
config-only change with zero lines touched in the agent core/loop.
"""

import json
import logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.agent.core.registry import ToolRegistry

logger = logging.getLogger(__name__)


class MCPTool:
    def __init__(self, name: str, description: str, parameters_schema: dict, session: ClientSession):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
        self._session = session

    async def call(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self._session.call_tool(self.name, args)
        return _unwrap(result)


def _unwrap(result) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if structured:
        return structured
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
    return {}


async def build_mcp_registry(config_path: str | Path) -> tuple[ToolRegistry, AsyncExitStack]:
    """Reads config_path (a JSON file: {"servers": [{"name","command","args","env"},...]}),
    connects to every listed server over stdio, and discovers its tools via a
    real tools/list call. Returns (registry, exit_stack) - the caller owns the
    exit_stack's lifetime and must `await exit_stack.aclose()` on shutdown."""
    config = json.loads(Path(config_path).read_text())
    stack = AsyncExitStack()
    tools = []
    for server_cfg in config["servers"]:
        params = StdioServerParameters(
            command=server_cfg["command"],
            args=server_cfg.get("args", []),
            env=server_cfg.get("env") or None,
        )
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        listed = await session.list_tools()
        logger.info("mcp server=%s discovered %d tools: %s", server_cfg["name"], len(listed.tools),
                    [t.name for t in listed.tools])
        for t in listed.tools:
            tools.append(MCPTool(t.name, t.description or "", t.inputSchema or {}, session))
    return ToolRegistry(tools=tools), stack
