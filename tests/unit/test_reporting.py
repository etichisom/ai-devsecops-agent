import json
from xml.etree import ElementTree as ET

import pytest

from devsecops_agent.reporting import (
    gate,
    severity_counts,
    sort_findings,
    to_json,
    to_junit,
    to_markdown,
    write_reports,
)
from devsecops_agent.security import Finding, Severity

LOW = Finding("bandit", "SAST", "B105", Severity.LOW, "hardcoded | password", "cfg.py", 5)
HIGH = Finding("semgrep", "SAST", "shell-true", Severity.HIGH, "shell=True", "utils.py", 12, fix="use a list argv")
MED = Finding("pip-audit", "SCA", "GHSA-1", Severity.MEDIUM, "leaks header", "requests==2.25.0")


def test_sort_puts_most_severe_first():
    assert sort_findings([LOW, HIGH, MED]) == [HIGH, MED, LOW]


def test_severity_counts_include_zero_buckets():
    counts = severity_counts([LOW, HIGH])
    assert list(counts) == ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    assert counts["HIGH"] == 1 and counts["CRITICAL"] == 0


@pytest.mark.parametrize(
    "fail_on, expected",
    [("critical", False), ("high", True), ("medium", True), ("none", False), (None, False)],
)
def test_gate(fail_on, expected):
    assert gate([LOW, HIGH], fail_on) is expected


def test_markdown_escapes_pipes_and_includes_summary():
    md = to_markdown([LOW, HIGH], summary="Fix shell=True first.")
    assert "hardcoded \\| password" in md
    assert "## AI triage summary" in md
    assert md.index("shell-true") < md.index("B105")


def test_markdown_no_findings():
    assert "No findings" in to_markdown([])


def test_json_report():
    data = json.loads(to_json([LOW, HIGH]))
    assert data["total"] == 2
    assert data["findings"][0]["severity"] == "HIGH"


def test_junit_marks_only_findings_over_threshold_as_failures():
    suite = ET.fromstring(to_junit([LOW, HIGH, MED], fail_on="medium"))
    assert suite.get("tests") == "3" and suite.get("failures") == "2"
    assert len(suite.findall("testcase/failure")) == 2
    assert len(suite.findall("testcase/system-out")) == 1


def test_junit_empty_still_valid():
    suite = ET.fromstring(to_junit([]))
    assert suite.get("failures") == "0" and len(suite.findall("testcase")) == 1


def test_write_reports(tmp_path):
    paths = write_reports(tmp_path / "out", [HIGH])
    assert sorted(p.name for p in paths) == ["security-junit.xml", "security-report.json", "security-report.md"]
    assert all(p.stat().st_size > 0 for p in paths)
