"""End-to-end CLI tests: argument parsing, report files and exit codes."""

import json

import pytest

from devsecops_agent import cli
from devsecops_agent.security import Finding, ScanResult, Severity

pytestmark = pytest.mark.integration


def test_report_from_fixture_files_fails_gate_on_high(fixtures, tmp_path, capsys):
    out = tmp_path / "reports"
    code = cli.main(
        [
            "report",
            "--semgrep",
            str(fixtures / "semgrep.json"),
            "--bandit",
            str(fixtures / "bandit.json"),
            "--pip-audit",
            str(fixtures / "pip-audit.json"),
            "--gitleaks",
            str(fixtures / "gitleaks.json"),
            "--out",
            str(out),
        ]
    )
    assert code == cli.EXIT_GATE_FAILED
    data = json.loads((out / "security-report.json").read_text())
    assert data["total"] == 6
    assert data["summary"]["HIGH"] == 2
    assert "6 findings" in capsys.readouterr().out


def test_report_passes_with_higher_threshold(fixtures, tmp_path):
    code = cli.main(["report", "--bandit", str(fixtures / "bandit.json"), "--out", str(tmp_path), "--fail-on", "high"])
    assert code == cli.EXIT_OK


def test_report_requires_an_input(tmp_path, capsys):
    assert cli.main(["report", "--out", str(tmp_path)]) == cli.EXIT_USAGE
    assert "at least one" in capsys.readouterr().err


def test_report_bad_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert cli.main(["report", "--semgrep", str(bad), "--out", str(tmp_path)]) == cli.EXIT_USAGE


def test_scan_uses_selected_scanners(monkeypatch, tmp_path):
    seen = {}

    def fake_run_scanners(path, tools):
        seen["tools"] = tools
        return [ScanResult("bandit", findings=[Finding("bandit", "SAST", "B1", Severity.LOW, "m", "a.py", 1)])]

    monkeypatch.setattr(cli, "run_scanners", fake_run_scanners)
    code = cli.main(["scan", str(tmp_path), "--scanners", "bandit", "--out", str(tmp_path / "r"), "--fail-on", "low"])
    assert seen["tools"] == ["bandit"]
    assert code == cli.EXIT_GATE_FAILED


def test_scan_rejects_unknown_scanner(tmp_path):
    assert cli.main(["scan", str(tmp_path), "--scanners", "nmap"]) == cli.EXIT_USAGE


def test_ai_summary_skipped_without_key(monkeypatch, fixtures, tmp_path, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cli.main(["report", "--bandit", str(fixtures / "bandit.json"), "--out", str(tmp_path), "--ai-summary"])
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err
