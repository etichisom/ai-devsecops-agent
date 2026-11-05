"""File tools, sandboxed to a workspace directory so the model cannot touch files outside it."""

from __future__ import annotations

from pathlib import Path

from .base import Tool, ToolError

MAX_READ_BYTES = 200_000


class Workspace:
    """Resolves paths relative to a root and refuses anything that escapes it (../, absolute paths, symlinks)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def resolve(self, path: str = "") -> Path:
        candidate = (self.root / (path or ".")).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ToolError(f"Path is outside the workspace: {path}")
        return candidate

    def read_file(self, path: str) -> str:
        target = self.resolve(path)
        if not target.is_file():
            raise ToolError(f"File not found: {path}")
        if target.stat().st_size > MAX_READ_BYTES:
            raise ToolError(f"File is larger than {MAX_READ_BYTES} bytes: {path}")
        return target.read_text(encoding="utf-8", errors="replace")

    def list_files(self, path: str = "") -> str:
        target = self.resolve(path)
        if not target.is_dir():
            raise ToolError(f"Directory not found: {path or '.'}")
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        if not entries:
            return f"Empty directory: {path or '.'}"
        lines = [f"[dir]  {p.name}/" if p.is_dir() else f"[file] {p.name}" for p in entries]
        return f"Contents of {path or '.'}:\n" + "\n".join(lines)

    def edit_file(self, path: str, new_text: str, old_text: str = "") -> str:
        target = self.resolve(path)
        if not target.exists():
            if old_text:
                raise ToolError(f"File not found: {path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_text, encoding="utf-8")
            return f"Created {path}"

        content = target.read_text(encoding="utf-8")
        if not old_text:
            raise ToolError(f"{path} already exists; pass old_text to edit it")
        count = content.count(old_text)
        if count == 0:
            raise ToolError(f"old_text not found in {path}")
        if count > 1:
            raise ToolError(f"old_text matches {count} places in {path}; make it unique")
        target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"


def filesystem_tools(workspace: Workspace) -> list[Tool]:
    return [
        Tool(
            name="read_file",
            description="Read a UTF-8 text file inside the workspace.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path relative to the workspace root"}},
                "required": ["path"],
            },
            handler=workspace.read_file,
        ),
        Tool(
            name="list_files",
            description="List the files and folders in a workspace directory.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory relative to the workspace root (default: root)",
                    }
                },
                "required": [],
            },
            handler=workspace.list_files,
        ),
        Tool(
            name="edit_file",
            description=(
                "Edit a file by replacing one unique occurrence of old_text with new_text. "
                "Leave old_text empty to create a new file."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the workspace root"},
                    "old_text": {"type": "string", "description": "Exact text to replace (empty to create a file)"},
                    "new_text": {"type": "string", "description": "Replacement text, or the new file's content"},
                },
                "required": ["path", "new_text"],
            },
            handler=workspace.edit_file,
        ),
    ]
