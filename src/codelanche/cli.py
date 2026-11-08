"""Command-line interface for Codelanche AI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from codelanche import __version__
from codelanche.agents.harness import (
    AgentRuntimeError,
    CodelancheHarness,
    EvidenceVerificationError,
)
from codelanche.impact import analyze_impact
from codelanche.scanner import scan_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codelanche",
        description="Local AI agents for repository intelligence and change-impact analysis.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="build a deterministic repository graph")
    scan.add_argument("repository", nargs="?", default=".")
    scan.add_argument("--json", action="store_true", dest="as_json")

    impact = subparsers.add_parser("impact", help="calculate a file or symbol blast radius")
    impact.add_argument("target")
    impact.add_argument("--repo", default=".", dest="repository")
    impact.add_argument("--depth", type=int, default=4)
    impact.add_argument("--json", action="store_true", dest="as_json")
    impact.add_argument(
        "--ai",
        action="store_true",
        help="ask the grounded local Impact Agent to explain the result",
    )
    impact.add_argument("--model", help="Ollama model name (default: CODELANCHE_MODEL)")

    doctor = subparsers.add_parser("doctor", help="check local runtime prerequisites")
    doctor.add_argument("--ollama-url", default="http://localhost:11434")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan":
            _scan(args.repository, args.as_json)
        elif args.command == "impact":
            _impact(
                args.repository,
                args.target,
                args.depth,
                args.as_json,
                args.ai,
                args.model,
            )
        elif args.command == "doctor":
            _doctor(args.ollama_url)
    except (
        AgentRuntimeError,
        FileNotFoundError,
        NotADirectoryError,
        ValueError,
        EvidenceVerificationError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _scan(repository: str, as_json: bool) -> None:
    graph = scan_repository(repository)
    if as_json:
        print(json.dumps(graph.to_dict(), indent=2))
        return
    summary = graph.to_dict()["summary"]
    print(f"Codelanche scanned {graph.root}")
    print(
        f"  {summary['file_count']} files · {summary['node_count']} nodes · "
        f"{summary['edge_count']} edges"
    )
    for warning in graph.warnings:
        print(f"  warning: {warning}")


def _impact(
    repository: str,
    target: str,
    depth: int,
    as_json: bool,
    use_ai: bool,
    model: str | None,
) -> None:
    graph = scan_repository(repository)
    if use_ai:
        result = CodelancheHarness(graph, model_name=model).impact(
            target, max_depth=depth, use_ai=True
        )
        payload = result.report.to_dict()
        payload["agent_explanation"] = (
            result.explanation.model_dump() if result.explanation is not None else None
        )
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            _print_report(result.report)
            if result.explanation:
                print("\nImpact Agent")
                print(f"  {result.explanation.summary}")
                for reason in result.explanation.reasoning:
                    print(f"  - {reason}")
        return

    report = analyze_impact(graph, target, max_depth=depth)
    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_report(report)


def _print_report(report) -> None:
    if report.warnings:
        for warning in report.warnings:
            print(f"warning: {warning}")
        return
    print(f"Impact: {report.query}")
    print(f"  Risk: {report.risk.upper()} ({report.score}/100)")
    print(f"  Matched: {len(report.matched)}")
    print(f"  Impacted nodes: {len(report.impacted)}")
    print(f"  Impacted files: {len(report.impacted_files)}")
    if report.impacted_files:
        print("\nAffected files")
        for path in report.impacted_files:
            print(f"  - {path}")
    if report.recommended_tests:
        print("\nRecommended tests")
        for path in report.recommended_tests:
            print(f"  - {path}")


def _doctor(ollama_url: str) -> None:
    import urllib.error
    import urllib.request

    print(f"Codelanche AI {__version__}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Working directory: {Path.cwd()}")
    try:
        with urllib.request.urlopen(ollama_url, timeout=2) as response:
            status = response.status
    except (urllib.error.URLError, TimeoutError):
        print(f"  Ollama: unavailable at {ollama_url} (AI explanations disabled)")
    else:
        print(f"  Ollama: available at {ollama_url} (HTTP {status})")


if __name__ == "__main__":
    main()
