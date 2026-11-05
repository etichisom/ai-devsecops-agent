"""Turn findings into reports (Markdown, JSON, JUnit XML) and apply a severity gate for CI."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET  # nosec B405 - only used to build XML, never to parse untrusted input

from .security import Finding, ScanResult, Severity


def sort_findings(findings: Iterable[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (-f.severity, f.tool, f.location, f.line or 0))


def severity_counts(findings: Iterable[Finding]) -> dict[str, int]:
    counts = Counter(f.severity.name for f in findings)
    return {s.name: counts.get(s.name, 0) for s in sorted(Severity, reverse=True)}


def gate(findings: Iterable[Finding], fail_on: str | None) -> bool:
    """Return True when the build should fail: any finding at or above fail_on. None or 'none' never fails."""
    if not fail_on or fail_on.lower() == "none":
        return False
    threshold = Severity.parse(fail_on)
    return any(f.severity >= threshold for f in findings)


def _escape_md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(findings: list[Finding], results: list[ScanResult] | None = None, summary: str | None = None) -> str:
    findings = sort_findings(findings)
    counts = severity_counts(findings)
    lines = [
        "# Security Scan Report",
        "",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}_",
        "",
        "| " + " | ".join(counts) + " | Total |",
        "|" + "---|" * (len(counts) + 1),
        "| " + " | ".join(str(v) for v in counts.values()) + f" | {len(findings)} |",
        "",
    ]
    if results:
        lines += ["## Scanners", ""]
        for r in results:
            status = "skipped" if r.skipped else ("error" if r.error else f"{len(r.findings)} findings")
            note = f" ({r.error})" if r.error else ""
            lines.append(f"- **{r.tool}**: {status}{note}")
        lines.append("")
    if summary:
        lines += ["## AI triage summary", "", summary.strip(), ""]
    lines += ["## Findings", ""]
    if not findings:
        lines.append("No findings. :white_check_mark:")
    else:
        lines += ["| Severity | Tool | Rule | Location | Message | Fix |", "|---|---|---|---|---|---|"]
        for f in findings:
            loc = f"{f.location}:{f.line}" if f.line else f.location
            lines.append(
                f"| {f.severity.name} | {f.tool} | `{_escape_md(f.rule_id)}` | `{_escape_md(loc)}` "
                f"| {_escape_md(f.message)[:200]} | {_escape_md(f.fix or '')[:120]} |"
            )
    return "\n".join(lines) + "\n"


def to_json(findings: list[Finding]) -> str:
    findings = sort_findings(findings)
    return json.dumps(
        {"summary": severity_counts(findings), "total": len(findings), "findings": [f.to_dict() for f in findings]},
        indent=2,
    )


def to_junit(findings: list[Finding], fail_on: str = "high") -> str:
    """JUnit XML so Jenkins and GitLab show findings in their test report UI.

    Findings at or above fail_on become <failure>; lower ones are recorded as passing test cases with output.
    """
    threshold = Severity.parse(fail_on) if fail_on and fail_on.lower() != "none" else Severity.CRITICAL + 1
    findings = sort_findings(findings)
    failures = sum(1 for f in findings if f.severity >= threshold)
    suite = ET.Element("testsuite", name="security-scan", tests=str(max(len(findings), 1)), failures=str(failures))
    if not findings:
        ET.SubElement(suite, "testcase", classname="security", name="no-findings")
    for f in findings:
        case = ET.SubElement(
            suite, "testcase", classname=f"security.{f.tool}", name=f"{f.rule_id} @ {f.location}:{f.line or 0}"
        )
        body = f"{f.severity.name}: {f.message}" + (f"\nFix: {f.fix}" if f.fix else "")
        if f.severity >= threshold:
            ET.SubElement(case, "failure", message=f.severity.name, type=f.category).text = body
        else:
            ET.SubElement(case, "system-out").text = body
    return ET.tostring(suite, encoding="unicode")


def write_reports(
    out_dir: str | Path,
    findings: list[Finding],
    results: list[ScanResult] | None = None,
    summary: str | None = None,
    fail_on: str = "high",
) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "security-report.md": to_markdown(findings, results, summary),
        "security-report.json": to_json(findings),
        "security-junit.xml": to_junit(findings, fail_on),
    }
    paths = []
    for name, content in files.items():
        path = out / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths
