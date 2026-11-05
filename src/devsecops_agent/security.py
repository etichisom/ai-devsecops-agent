"""Run security scanners and normalise their JSON output into one Finding model.

Supported scanners:
    semgrep   - SAST (multi-language rules)
    bandit    - SAST (Python)
    pip-audit - SCA (known-vulnerable Python dependencies)
    gitleaks  - secret detection

Each scanner has a parser that turns its JSON into Findings, so reports and CI gates
work the same way no matter which tool produced the data. Parsers are pure functions
and are tested against recorded fixtures in tests/fixtures.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 - scanners run with a fixed argv, never a shell
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from enum import IntEnum
from pathlib import Path
from typing import Any


class Severity(IntEnum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def parse(cls, value: str | None, default: Severity | None = None) -> Severity:
        aliases = {"ERROR": "HIGH", "WARNING": "MEDIUM", "WARN": "MEDIUM", "NOTE": "LOW", "UNDEFINED": "INFO"}
        key = (value or "").strip().upper()
        key = aliases.get(key, key)
        if key in cls.__members__:
            return cls[key]
        if default is not None:
            return default
        raise ValueError(f"Unknown severity: {value}")


@dataclass(frozen=True)
class Finding:
    tool: str
    category: str  # SAST | SCA | SECRETS
    rule_id: str
    severity: Severity
    message: str
    location: str  # file path, or package==version for SCA
    line: int | None = None
    cwe: str | None = None
    fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.name
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        return cls(**{**data, "severity": Severity.parse(data["severity"])})


@dataclass
class ScanResult:
    tool: str
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None
    skipped: bool = False


# --------------------------------------------------------------------------- parsers


def _first(value: Any) -> str | None:
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value else None


def parse_semgrep(data: dict[str, Any]) -> list[Finding]:
    findings = []
    for r in data.get("results", []):
        extra = r.get("extra", {})
        meta = extra.get("metadata", {})
        findings.append(
            Finding(
                tool="semgrep",
                category="SAST",
                rule_id=r.get("check_id", "unknown"),
                severity=Severity.parse(extra.get("severity"), Severity.MEDIUM),
                message=extra.get("message", "").strip(),
                location=r.get("path", ""),
                line=r.get("start", {}).get("line"),
                cwe=_first(meta.get("cwe")),
                fix=extra.get("fix"),
            )
        )
    return findings


def parse_bandit(data: dict[str, Any]) -> list[Finding]:
    findings = []
    for r in data.get("results", []):
        cwe = r.get("issue_cwe") or {}
        findings.append(
            Finding(
                tool="bandit",
                category="SAST",
                rule_id=f"{r.get('test_id', '')}:{r.get('test_name', '')}".strip(":"),
                severity=Severity.parse(r.get("issue_severity"), Severity.MEDIUM),
                message=r.get("issue_text", "").strip(),
                location=r.get("filename", ""),
                line=r.get("line_number"),
                cwe=f"CWE-{cwe['id']}" if cwe.get("id") else None,
            )
        )
    return findings


def parse_pip_audit(data: dict[str, Any] | list[Any]) -> list[Finding]:
    # pip-audit >= 2.5 wraps the list in {"dependencies": [...]}; older versions return the list.
    deps = data.get("dependencies", []) if isinstance(data, dict) else data
    findings = []
    for dep in deps:
        for vuln in dep.get("vulns", []):
            fixes = vuln.get("fix_versions") or []
            aliases = vuln.get("aliases") or []
            findings.append(
                Finding(
                    tool="pip-audit",
                    category="SCA",
                    rule_id=vuln.get("id", "unknown"),
                    # pip-audit does not report severity; treat a known CVE as MEDIUM until triaged.
                    severity=Severity.MEDIUM,
                    message=(vuln.get("description") or ", ".join(aliases) or "Known vulnerability").strip(),
                    location=f"{dep.get('name')}=={dep.get('version')}",
                    fix=f"Upgrade to {', '.join(fixes)}" if fixes else None,
                )
            )
    return findings


def parse_gitleaks(data: list[dict[str, Any]] | None) -> list[Finding]:
    # The secret value is never copied into a Finding, so reports cannot leak it.
    return [
        Finding(
            tool="gitleaks",
            category="SECRETS",
            rule_id=leak.get("RuleID", "unknown"),
            severity=Severity.HIGH,
            message=leak.get("Description", "Possible secret"),
            location=leak.get("File", ""),
            line=leak.get("StartLine"),
            fix="Remove the secret, rotate it, and load it from the environment or a secret store",
        )
        for leak in data or []
    ]


PARSERS: dict[str, Callable[[Any], list[Finding]]] = {
    "semgrep": parse_semgrep,
    "bandit": parse_bandit,
    "pip-audit": parse_pip_audit,
    "gitleaks": parse_gitleaks,
}
SCANNERS = tuple(PARSERS)


# --------------------------------------------------------------------------- runners

EXCLUDES = (".venv", "venv", ".git", "node_modules", "__pycache__", "reports")


def _command(tool: str, target: Path, report_file: Path) -> list[str]:
    if tool == "semgrep":
        cmd = ["semgrep", "scan", "--config", "p/default", "--json", "--quiet", "--metrics=off"]
        for ex in EXCLUDES:
            cmd += ["--exclude", ex]
        return cmd + [str(target)]
    if tool == "bandit":
        excludes = ",".join(str(target / ex) for ex in (*EXCLUDES, "tests"))
        return ["bandit", "-r", str(target), "-f", "json", "-q", "-x", excludes]
    if tool == "pip-audit":
        req = target / "requirements.txt"
        base = ["pip-audit", "-f", "json", "--progress-spinner", "off"]
        return base + (["-r", str(req)] if req.is_file() else [])
    if tool == "gitleaks":
        return [
            "gitleaks",
            "detect",
            "--source",
            str(target),
            "--no-git",
            "--redact",
            "--no-banner",
            "--report-format",
            "json",
            "--report-path",
            str(report_file),
            "--exit-code",
            "0",
        ]
    raise ValueError(f"Unknown scanner: {tool}")


def _relative(finding: Finding, root: Path) -> Finding:
    """Report file paths relative to the scan root so reports are portable across CI runners."""
    path = Path(finding.location)
    if path.is_absolute() and path.is_relative_to(root):
        return replace(finding, location=str(path.relative_to(root)))
    return finding


def run_scanner(tool: str, target: str | Path, timeout: int = 600) -> ScanResult:
    """Run one scanner against target. Missing binaries are reported as skipped, not as failures."""
    if tool not in PARSERS:
        return ScanResult(tool, error=f"Unknown scanner: {tool}")
    if shutil.which(tool) is None:
        return ScanResult(tool, skipped=True, error=f"{tool} is not installed")

    target = Path(target).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        report_file = Path(tmp) / "report.json"
        try:
            proc = subprocess.run(  # noqa: S603 # nosec B603 - fixed argv, no shell
                _command(tool, target, report_file), capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            return ScanResult(tool, error=f"{tool} timed out after {timeout}s")

        raw = report_file.read_text() if report_file.exists() else proc.stdout
    # Most scanners exit non-zero when they find issues, so the exit code alone is not an error.
    try:
        data = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        return ScanResult(
            tool, error=f"{tool} did not return JSON (exit {proc.returncode}): {proc.stderr.strip()[:300]}"
        )
    findings = PARSERS[tool](data or ({} if tool != "gitleaks" else []))
    return ScanResult(tool, findings=[_relative(f, target) for f in findings])


def run_scanners(target: str | Path, tools: list[str] | None = None) -> list[ScanResult]:
    return [run_scanner(tool, target) for tool in (tools or list(SCANNERS))]


def load_report(tool: str, path: str | Path) -> list[Finding]:
    """Parse a scanner report produced elsewhere, e.g. by a separate CI job."""
    if tool not in PARSERS:
        raise ValueError(f"Unknown scanner: {tool}. Choose from {', '.join(SCANNERS)}")
    return PARSERS[tool](json.loads(Path(path).read_text()))
