"""Exposes the security scanners to the model as a tool."""

from __future__ import annotations

import json

from ..reporting import severity_counts, sort_findings
from ..security import SCANNERS, run_scanners
from .base import Tool, ToolError
from .filesystem import Workspace

MAX_FINDINGS_FOR_MODEL = 50


def security_scan(workspace: Workspace, path: str = "", scanners: list[str] | None = None) -> str:
    target = workspace.resolve(path)
    if not target.exists():
        raise ToolError(f"Path not found: {path or '.'}")
    unknown = set(scanners or []) - set(SCANNERS)
    if unknown:
        raise ToolError(f"Unknown scanners: {', '.join(sorted(unknown))}")

    results = run_scanners(target, scanners)
    findings = sort_findings(f for r in results for f in r.findings)
    payload = {
        "scanners": {r.tool: (r.error or f"{len(r.findings)} findings") for r in results},
        "summary": severity_counts(findings),
        "total": len(findings),
        "findings": [f.to_dict() for f in findings[:MAX_FINDINGS_FOR_MODEL]],
    }
    if len(findings) > MAX_FINDINGS_FOR_MODEL:
        payload["truncated"] = f"Showing the {MAX_FINDINGS_FOR_MODEL} most severe of {len(findings)} findings"
    return json.dumps(payload, indent=2)


def security_tools(workspace: Workspace) -> list[Tool]:
    return [
        Tool(
            name="security_scan",
            description=(
                "Run security scanners on a workspace path and return normalised findings as JSON. "
                "semgrep and bandit do SAST, pip-audit checks dependencies for known CVEs (SCA), "
                "gitleaks looks for committed secrets. Use read_file afterwards to inspect flagged code."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the workspace root (default: root)"},
                    "scanners": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(SCANNERS)},
                        "description": "Scanners to run (default: all installed)",
                    },
                },
                "required": [],
            },
            handler=lambda **kw: security_scan(workspace, **kw),
        )
    ]
