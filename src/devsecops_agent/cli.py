"""Command-line entry point.

devsecops-agent chat                       interactive agent
devsecops-agent scan [PATH]                run scanners, write reports, fail on a severity threshold
devsecops-agent report --semgrep s.json    build reports from scanner output produced by other CI jobs
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .reporting import gate, severity_counts, to_json, write_reports
from .security import SCANNERS, Finding, ScanResult, load_report, run_scanners

EXIT_OK, EXIT_GATE_FAILED, EXIT_USAGE = 0, 1, 2
SEVERITY_CHOICES = ["critical", "high", "medium", "low", "info", "none"]


def _add_report_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("-o", "--out", default="reports", help="Directory for the reports (default: reports)")
    p.add_argument(
        "--fail-on",
        default="high",
        choices=SEVERITY_CHOICES,
        help="Exit 1 if any finding is at or above this severity (default: high)",
    )
    p.add_argument(
        "--ai-summary", action="store_true", help="Add a Claude-written triage summary (needs ANTHROPIC_API_KEY)"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="devsecops-agent",
        description="Run SAST/SCA/secret scanners, report and gate CI builds, and chat with a Claude security agent.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log tool calls and API activity")
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="Start the interactive agent")
    chat.add_argument("-w", "--workspace", default=".", help="Directory the agent may read and edit (default: .)")
    chat.add_argument("--model", help="Claude model id (default: $CLAUDE_MODEL or claude-sonnet-5-5)")

    scan = sub.add_parser("scan", help="Run security scanners and write reports")
    scan.add_argument("path", nargs="?", default=".", help="Directory to scan (default: .)")
    scan.add_argument(
        "-s",
        "--scanners",
        default=",".join(SCANNERS),
        help=f"Comma-separated scanners to run (default: {','.join(SCANNERS)})",
    )
    _add_report_options(scan)

    report = sub.add_parser("report", help="Build reports from existing scanner JSON files")
    for tool in SCANNERS:
        report.add_argument(f"--{tool}", dest=tool.replace("-", "_"), metavar="FILE", help=f"{tool} JSON output")
    _add_report_options(report)
    return parser


def _finish(findings: list[Finding], results: list[ScanResult] | None, args: argparse.Namespace) -> int:
    summary = None
    if args.ai_summary:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("warning: --ai-summary skipped, ANTHROPIC_API_KEY is not set", file=sys.stderr)
        elif findings:
            from .agent import summarize_findings

            try:
                summary = summarize_findings(to_json(findings))
            except Exception as exc:  # noqa: BLE001 - AI summary is optional; never fail the build on it
                print(f"warning: AI summary failed: {exc}", file=sys.stderr)

    paths = write_reports(args.out, findings, results, summary, args.fail_on)
    counts = ", ".join(f"{k.lower()}={v}" for k, v in severity_counts(findings).items())
    print(f"{len(findings)} findings ({counts})")
    for p in paths:
        print(f"  wrote {p}")

    if gate(findings, args.fail_on):
        print(f"FAILED: findings at or above '{args.fail_on}'", file=sys.stderr)
        return EXIT_GATE_FAILED
    return EXIT_OK


def cmd_scan(args: argparse.Namespace) -> int:
    tools = [t.strip() for t in args.scanners.split(",") if t.strip()]
    unknown = set(tools) - set(SCANNERS)
    if unknown:
        print(f"error: unknown scanners: {', '.join(sorted(unknown))}", file=sys.stderr)
        return EXIT_USAGE
    if not Path(args.path).is_dir():
        print(f"error: not a directory: {args.path}", file=sys.stderr)
        return EXIT_USAGE

    results = run_scanners(args.path, tools)
    for r in results:
        if r.error:
            print(f"warning: {r.tool}: {r.error}", file=sys.stderr)
    return _finish([f for r in results for f in r.findings], results, args)


def cmd_report(args: argparse.Namespace) -> int:
    inputs = {tool: getattr(args, tool.replace("-", "_")) for tool in SCANNERS}
    inputs = {tool: path for tool, path in inputs.items() if path}
    if not inputs:
        print("error: pass at least one scanner report, e.g. --semgrep semgrep.json", file=sys.stderr)
        return EXIT_USAGE

    findings: list[Finding] = []
    results: list[ScanResult] = []
    for tool, path in inputs.items():
        try:
            parsed = load_report(tool, path)
        except (OSError, ValueError) as exc:
            print(f"error: could not read {tool} report {path}: {exc}", file=sys.stderr)
            return EXIT_USAGE
        findings += parsed
        results.append(ScanResult(tool, findings=parsed))
    return _finish(findings, results, args)


def cmd_chat(args: argparse.Namespace) -> int:
    from rich.console import Console

    from .agent import Agent
    from .tools import Workspace, default_registry

    console = Console()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[yellow]ANTHROPIC_API_KEY is not set; the SDK will try other configured credentials.[/yellow]")

    workspace = Workspace(args.workspace)
    agent = Agent(default_registry(workspace), model=args.model)
    console.print(f"[bold]DevSecOps Agent[/bold] v{__version__}  model={agent.model}  workspace={workspace.root}")
    console.print("Type 'exit' to quit, 'reset' to clear the conversation.\n")

    while True:
        try:
            user_input = console.input("[bold green]you>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return EXIT_OK
        if user_input.lower() in {"exit", "quit"}:
            return EXIT_OK
        if user_input.lower() == "reset":
            agent.reset()
            console.print("[dim]conversation cleared[/dim]")
            continue
        if not user_input:
            continue
        try:
            with console.status("[cyan]thinking...[/cyan]", spinner="dots"):
                answer = agent.chat(user_input)
        except Exception as exc:  # noqa: BLE001 - keep the session alive on API errors
            console.print(f"[red]error:[/red] {exc}")
            continue
        console.print(f"[bold cyan]agent>[/bold cyan] {answer}\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    handlers = {"chat": cmd_chat, "scan": cmd_scan, "report": cmd_report}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
