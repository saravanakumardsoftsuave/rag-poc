"""Generic tool registry. Deliberately knows nothing about MCP or about any
specific tool implementation - it is the one seam that lets the agentic loop
(loop.py) stay byte-for-byte identical whether its tools come from plain
Python functions or from an MCP server's tools/list response."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


class Tool(Protocol):
    name: str
    description: str
    parameters_schema: dict[str, Any]

    async def call(self, args: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class LocalTool:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    _fn: Callable[..., dict[str, Any]]

    async def call(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._fn(**args)


@dataclass
class ToolRegistry:
    tools: list[Tool] = field(default_factory=list)

    def get(self, name: str) -> Tool | None:
        return next((t for t in self.tools if t.name == name), None)

    def names(self) -> list[str]:
        return [t.name for t in self.tools]

    def as_prompt_block(self) -> str:
        lines = []
        for tool in self.tools:
            params = ", ".join(tool.parameters_schema.get("properties", {}).keys())
            lines.append(f"- {tool.name}({params}): {tool.description}")
        return "\n".join(lines)


def _schema_from_function(fn: Callable) -> dict[str, Any]:
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required = []
    for param_name, param in sig.parameters.items():
        properties[param_name] = {"type": _type_name(param.annotation)}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    return {"type": "object", "properties": properties, "required": required}


def _type_name(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty:
        return "any"
    return getattr(annotation, "__name__", str(annotation))


def local_registry(*functions: Callable[..., dict[str, Any]]) -> ToolRegistry:
    """Wraps plain Python functions (each must return a dict and have a
    one-line-or-more docstring used as its tool description) into a
    ToolRegistry with the same shape an MCP-backed registry would have."""
    tools: list[Tool] = []
    for fn in functions:
        description = (fn.__doc__ or fn.__name__).strip().split("\n")[0]
        tools.append(LocalTool(
            name=fn.__name__,
            description=description,
            parameters_schema=_schema_from_function(fn),
            _fn=fn,
        ))
    return ToolRegistry(tools=tools)
