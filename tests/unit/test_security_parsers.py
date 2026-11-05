import json
import subprocess

import pytest

from devsecops_agent import security
from devsecops_agent.security import Finding, Severity, load_report, run_scanner


@pytest.mark.parametrize(
    "raw, expected",
    [("ERROR", Severity.HIGH), ("warning", Severity.MEDIUM), ("CRITICAL", Severity.CRITICAL), (" low ", Severity.LOW)],
)
def test_severity_parse(raw, expected):
    assert Severity.parse(raw) is expected


def test_severity_parse_unknown_uses_default_or_raises():
    assert Severity.parse("weird", Severity.LOW) is Severity.LOW
    with pytest.raises(ValueError):
        Severity.parse("weird")


def test_parse_semgrep(fixtures):
    findings = load_report("semgrep", fixtures / "semgrep.json")
    assert len(findings) == 2
    first = findings[0]
    assert first.severity is Severity.HIGH
    assert first.location == "app/utils.py" and first.line == 12
    assert first.cwe.startswith("CWE-78")
    assert findings[1].cwe.startswith("CWE-489")  # string-form cwe also handled


def test_parse_bandit(fixtures):
    findings = load_report("bandit", fixtures / "bandit.json")
    assert [f.rule_id for f in findings] == ["B608:hardcoded_sql_expressions", "B105:hardcoded_password_string"]
    assert findings[0].cwe == "CWE-89"
    assert findings[1].severity is Severity.LOW


def test_parse_pip_audit_new_and_legacy_format(fixtures):
    data = json.loads((fixtures / "pip-audit.json").read_text())
    new = security.parse_pip_audit(data)
    legacy = security.parse_pip_audit(data["dependencies"])
    assert new == legacy
    assert len(new) == 1
    assert new[0].location == "requests==2.25.0"
    assert new[0].fix == "Upgrade to 2.31.0"
    assert new[0].category == "SCA"


def test_parse_gitleaks_never_includes_secret(fixtures):
    findings = load_report("gitleaks", fixtures / "gitleaks.json")
    assert findings[0].severity is Severity.HIGH
    assert "REDACTED" not in json.dumps([f.to_dict() for f in findings])


def test_finding_round_trip():
    f = Finding("bandit", "SAST", "B101", Severity.LOW, "assert used", "a.py", 3)
    assert Finding.from_dict(f.to_dict()) == f


def test_load_report_unknown_tool(fixtures):
    with pytest.raises(ValueError, match="Unknown scanner"):
        load_report("trivy", fixtures / "semgrep.json")


def test_run_scanner_skips_missing_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(security.shutil, "which", lambda _: None)
    result = run_scanner("bandit", tmp_path)
    assert result.skipped and "not installed" in result.error


def test_run_scanner_parses_stdout_and_ignores_nonzero_exit(monkeypatch, tmp_path, fixtures):
    monkeypatch.setattr(security.shutil, "which", lambda _: "/usr/bin/bandit")
    stdout = (fixtures / "bandit.json").read_text()

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "bandit" and "shell" not in kwargs
        return subprocess.CompletedProcess(cmd, returncode=1, stdout=stdout, stderr="")

    monkeypatch.setattr(security.subprocess, "run", fake_run)
    result = run_scanner("bandit", tmp_path)
    assert result.error is None
    assert len(result.findings) == 2


def test_run_scanner_reports_non_json_output(monkeypatch, tmp_path):
    monkeypatch.setattr(security.shutil, "which", lambda _: "/usr/bin/semgrep")
    monkeypatch.setattr(
        security.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, stdout="boom", stderr="config error"),
    )
    result = run_scanner("semgrep", tmp_path)
    assert "did not return JSON" in result.error and "config error" in result.error


def test_run_scanner_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(security.shutil, "which", lambda _: "/usr/bin/semgrep")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(security.subprocess, "run", fake_run)
    assert "timed out" in run_scanner("semgrep", tmp_path, timeout=1).error


def test_run_scanner_makes_paths_relative_to_target(monkeypatch, tmp_path):
    monkeypatch.setattr(security.shutil, "which", lambda _: "/usr/bin/bandit")
    out = json.dumps(
        {"results": [{"filename": str(tmp_path / "pkg" / "a.py"), "issue_severity": "LOW", "line_number": 1}]}
    )
    monkeypatch.setattr(
        security.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout=out, stderr="")
    )
    assert run_scanner("bandit", tmp_path).findings[0].location == "pkg/a.py"
