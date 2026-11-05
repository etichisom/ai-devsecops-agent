"""Tool model and registry used by the agent."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict


class Tool(BaseModel):
    """A tool the model can call: a JSON schema plus the Python function that runs it."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., str]

    def to_api(self) -> dict[str, Any]:
        """Return the tool definition in the shape the Messages API expects."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolError(Exception):
    """Raised by a tool when the call failed; the message is sent back to the model as an error result."""


class ToolRegistry:
    """Holds tools by name and dispatches calls to them."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.to_api() for tool in self._tools.values()]

    def execute(self, name: str, tool_input: dict[str, Any]) -> str:
        """Run a tool. Raises ToolError for unknown tools, bad input or tool failures."""
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"Unknown tool: {name}")
        try:
            return tool.handler(**tool_input)
        except ToolError:
            raise
        except TypeError as exc:
            raise ToolError(f"Invalid input for {name}: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - every failure is reported back to the model
            raise ToolError(f"{name} failed: {exc}") from exc
