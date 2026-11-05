"""Runs the real agent loop and real tools against a fake Claude client."""

import pytest

from devsecops_agent.agent import Agent, summarize_findings
from devsecops_agent.tools import default_registry
from tests.conftest import FakeClient, response, text_block, tool_use_block

pytestmark = pytest.mark.integration


def test_plain_answer(workspace):
    client = FakeClient([response(text_block("Hi there"))])
    agent = Agent(default_registry(workspace), client=client, model="test-model")
    assert agent.chat("hello") == "Hi there"
    assert client.requests[0]["model"] == "test-model"
    assert {t["name"] for t in client.requests[0]["tools"]} >= {"read_file", "security_scan"}


def test_tool_round_trip_keeps_history_valid(workspace):
    client = FakeClient(
        [
            response(
                text_block("Let me look."), tool_use_block("read_file", {"path": "src/app.py"}), stop_reason="tool_use"
            ),
            response(text_block("It prints hello.")),
        ]
    )
    agent = Agent(default_registry(workspace), client=client)

    assert agent.chat("what does app.py do?") == "It prints hello."

    roles = [m["role"] for m in agent.messages]
    assert roles == ["user", "assistant", "user", "assistant"]  # no empty/duplicate assistant turns
    tool_result = client.requests[1]["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "toolu_1"
    assert tool_result["is_error"] is False
    assert "print('hello')" in tool_result["content"]


def test_parallel_tool_calls_return_in_one_message(workspace):
    client = FakeClient(
        [
            response(
                tool_use_block("list_files", {}, "a"),
                tool_use_block("read_file", {"path": "README.md"}, "b"),
                stop_reason="tool_use",
            ),
            response(text_block("done")),
        ]
    )
    agent = Agent(default_registry(workspace), client=client)
    agent.chat("look around")
    results = agent.messages[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]


def test_tool_errors_are_sent_back_not_raised(workspace):
    client = FakeClient(
        [
            response(tool_use_block("read_file", {"path": "../../etc/passwd"}), stop_reason="tool_use"),
            response(text_block("I can't read files outside the workspace.")),
        ]
    )
    agent = Agent(default_registry(workspace), client=client)
    agent.chat("read /etc/passwd")
    result = agent.messages[2]["content"][0]
    assert result["is_error"] is True and "outside the workspace" in result["content"]


def test_refusal_and_max_tokens(workspace):
    agent = Agent(default_registry(workspace), client=FakeClient([response(stop_reason="refusal")]))
    assert "declined" in agent.chat("x")

    agent = Agent(
        default_registry(workspace), client=FakeClient([response(text_block("part"), stop_reason="max_tokens")])
    )
    assert "truncated" in agent.chat("x")


def test_loop_stops_after_max_rounds(workspace, monkeypatch):
    import devsecops_agent.agent as agent_mod

    monkeypatch.setattr(agent_mod, "MAX_TOOL_ROUNDS", 3)
    looping = [response(tool_use_block("list_files", {}), stop_reason="tool_use") for _ in range(3)]
    agent = Agent(default_registry(workspace), client=FakeClient(looping))
    assert "Stopped after 3" in agent.chat("loop forever")


def test_summarize_findings():
    client = FakeClient([response(text_block("Fix the SQL injection first."))])
    assert summarize_findings('{"findings": []}', client=client) == "Fix the SQL injection first."
    assert client.requests[0]["messages"][0]["content"] == '{"findings": []}'
