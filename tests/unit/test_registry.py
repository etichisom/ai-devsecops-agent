import json

import pytest

from devsecops_agent.security import Finding, ScanResult, Severity
from devsecops_agent.tools import Tool, ToolError, ToolRegistry, default_registry
from devsecops_agent.tools import security_scan as st


def _tool(name="echo", handler=lambda text: text):
    return Tool(name=name, description="d", input_schema={"type": "object"}, handler=handler)


def test_schemas_exclude_handler():
    schema = ToolRegistry([_tool()]).schemas()[0]
    assert set(schema) == {"name", "description", "input_schema"}


def test_duplicate_names_rejected():
    with pytest.raises(ValueError):
        ToolRegistry([_tool(), _tool()])


def test_execute_ok_and_errors():
    reg = ToolRegistry([_tool(), _tool("boom", lambda: 1 / 0)])
    assert reg.execute("echo", {"text": "hi"}) == "hi"
    with pytest.raises(ToolError, match="Unknown tool"):
        reg.execute("missing", {})
    with pytest.raises(ToolError, match="Invalid input"):
        reg.execute("echo", {"wrong": 1})
    with pytest.raises(ToolError, match="boom failed"):
        reg.execute("boom", {})


def test_default_registry_has_all_tools(workspace):
    reg = default_registry(workspace)
    for name in ["read_file", "list_files", "edit_file", "security_scan", "download_video", "split_video_into_frames"]:
        assert name in reg


def test_security_scan_tool_summarises_and_truncates(workspace, monkeypatch):
    many = [Finding("bandit", "SAST", f"B{i}", Severity.LOW, "m", "a.py", i) for i in range(60)]
    monkeypatch.setattr(st, "run_scanners", lambda target, tools: [ScanResult("bandit", findings=many)])
    out = json.loads(st.security_scan(workspace, scanners=["bandit"]))
    assert out["total"] == 60
    assert len(out["findings"]) == st.MAX_FINDINGS_FOR_MODEL
    assert "truncated" in out


def test_security_scan_tool_rejects_unknown_scanner(workspace):
    with pytest.raises(ToolError, match="Unknown scanners"):
        st.security_scan(workspace, scanners=["nmap"])


def test_download_video_rejects_non_http(workspace):
    from devsecops_agent.tools.video import download_video

    with pytest.raises(ToolError, match="http"):
        download_video(workspace, "file:///etc/passwd")
