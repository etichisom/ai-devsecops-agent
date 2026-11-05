from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from devsecops_agent.tools import Workspace

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    return Workspace(tmp_path)


# --- tiny fakes for the Anthropic client, so agent tests run offline -------------------------


def text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(name: str, tool_input: dict, block_id: str = "toolu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)


def response(*blocks, stop_reason: str = "end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class FakeClient:
    """Returns scripted responses in order and records every request."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        # Snapshot the message list, since the agent keeps appending to the same list object.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self._responses.pop(0)
