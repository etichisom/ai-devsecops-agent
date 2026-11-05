"""The agent loop: send the conversation to Claude, run any tools it asks for, repeat until it answers."""

from __future__ import annotations

import logging
import os
from typing import Any

import anthropic

from .tools import ToolError, ToolRegistry

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOOL_ROUNDS = 25

SYSTEM_PROMPT = """You are a DevSecOps assistant working in a terminal on the user's repository.
You can read, list and edit files in the workspace, run security scanners, and work with video files.

When asked about security:
- Run security_scan, then read the flagged code before judging a finding.
- Say when a finding looks like a false positive and why.
- Rank issues by real-world risk, not only by scanner severity.
- Suggest concrete fixes, and only edit files when the user asks you to.

Your output is shown in a plain terminal, so write plain text without Markdown formatting. Be concise."""


class Agent:
    def __init__(
        self,
        tools: ToolRegistry,
        client: Any | None = None,
        model: str | None = None,
        max_tokens: int = 16000,
    ) -> None:
        self.client = client or anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
        self.model = model or os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self.tools = tools
        self.messages: list[dict[str, Any]] = []

    def _run_tools(self, content: list[Any]) -> list[dict[str, Any]]:
        results = []
        for block in content:
            if block.type != "tool_use":
                continue
            log.info("tool call %s %s", block.name, block.input)
            try:
                output, is_error = self.tools.execute(block.name, dict(block.input)), False
            except ToolError as exc:
                output, is_error = str(exc), True
            log.info("tool result (%s chars, error=%s)", len(output), is_error)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error})
        return results

    def chat(self, user_input: str) -> str:
        """Send one user message and return Claude's final text answer, running tools along the way."""
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                tools=self.tools.schemas(),
                messages=self.messages,
            )
            # Keep the full content (including tool_use and thinking blocks) so the next request is valid.
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                return "The model declined this request."

            if response.stop_reason == "tool_use":
                # All results for one turn go back in a single user message.
                self.messages.append({"role": "user", "content": self._run_tools(response.content)})
                continue

            text = "\n".join(b.text for b in response.content if b.type == "text").strip()
            if response.stop_reason == "max_tokens":
                text += "\n[response truncated: max_tokens reached]"
            return text

        return f"Stopped after {MAX_TOOL_ROUNDS} tool rounds without a final answer."

    def reset(self) -> None:
        self.messages.clear()


TRIAGE_PROMPT = """You are a application security engineer triaging scanner output for a CI pipeline.
Given normalised findings as JSON, write a short Markdown summary for developers:
1. One sentence on overall risk.
2. The top issues to fix first, with file and line, and why they matter.
3. Findings that look like likely false positives or low priority, grouped.
Do not invent findings that are not in the input. Keep it under 300 words."""


def summarize_findings(findings_json: str, client: Any | None = None, model: str | None = None) -> str:
    """One-shot AI triage of a findings report, used by `devsecops-agent scan --ai-summary`."""
    client = client or anthropic.Anthropic()
    response = client.messages.create(
        model=model or os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL),
        max_tokens=4000,
        system=TRIAGE_PROMPT,
        messages=[{"role": "user", "content": findings_json}],
    )
    return "\n".join(b.text for b in response.content if b.type == "text").strip()
