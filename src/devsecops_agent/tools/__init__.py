"""Tools the agent can call."""

from .base import Tool, ToolError, ToolRegistry
from .filesystem import Workspace, filesystem_tools
from .security_scan import security_tools
from .video import video_tools


def default_registry(workspace: Workspace) -> ToolRegistry:
    return ToolRegistry([*filesystem_tools(workspace), *security_tools(workspace), *video_tools(workspace)])


__all__ = ["Tool", "ToolError", "ToolRegistry", "Workspace", "default_registry"]
