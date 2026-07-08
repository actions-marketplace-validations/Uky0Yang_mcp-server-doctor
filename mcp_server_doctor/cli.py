from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .checks import has_blocking_errors, run_static_checks
from .config import discover_config_paths, load_config
from .models import ConfigDocument, Finding, ProbeResult, ServerSpec
from .probe import probe_stdio_server

COMMANDS = {"check", "doctor", "list"}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        args.insert(0, "check")
    elif args[0] not in COMMANDS and args[0] not in ("-h", "--help"):
        args.insert(0, "check")
    namespace = build_parser().parse_args(args)
    if namespace.command == "list":
        return _cmd_list(namespace)
    if namespace.command == "check":
        return _cmd_check(namespace)
    if namespace.command == "doctor":
        return _cmd_doctor(namespace)
    raise AssertionError(namespace.command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-server-doctor",
        description="Diagnose MCP server config files and local stdio server startup.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Run static checks on MCP config files.")
    check.add_argument("paths", nargs="*", help="Config files or directories to scan. Defaults to current directory.")
    check.add_argument("--format", choices=("text", "json"), default="text")
    check.add_argument("--warnings-as-errors", action="store_true")

    doctor = subparsers.add_parser("doctor", help="Run static checks and stdio protocol probes.")
    doctor.add_argument("paths", nargs="*", help="Config files or directories to scan. Defaults to current directory.")
    doctor.add_argument("--server", action="append", help="Only probe this server name. Can be repeated.")
    doctor.add_argument("--timeout", type=float, default=8.0, help="Seconds to wait for each MCP response.")
    doctor.add_argument("--format", choices=("text", "json"), default="text")
    doctor.add_argument("--warnings-as-errors", action="store_true")

    list_cmd = subparsers.add_parser("list", help="List discovered MCP config files and servers.")
    list_cmd.add_argument("paths", nargs="*", help="Config files or directories to scan. Defaults to current directory.")
    list_cmd.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _cmd_list(args: argparse.Namespace) -> int:
    documents = _load_documents(args.paths)
    if args.format == "json":
        print(json.dumps({"configs": [doc.to_dict() for doc in documents]}, indent=2))
    else:
        if not documents:
            print("No MCP config files found.")
            return 0
        for document in documents:
            print(document.path)
            for server in document.servers:
                print(f"  - {server.name} ({server.transport})")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    documents = _load_documents(args.paths)
    findings = _all_static_findings(documents)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "ok": _is_ok(findings, args.warnings_as_errors),
                    "configs": [doc.to_dict() for doc in documents],
                    "findings": [finding.to_dict() for finding in findings],
                },
                indent=2,
            )
        )
    else:
        _print_static_report(documents, findings)
    return _exit_code(findings, args.warnings_as_errors)


def _cmd_doctor(args: argparse.Namespace) -> int:
    documents = _load_documents(args.paths)
    findings = _all_static_findings(documents)
    selected = set(args.server or [])
    probes: list[ProbeResult] = []

    if not has_blocking_errors(findings):
        for server in _all_servers(documents):
            if selected and server.name not in selected:
                continue
            probes.append(probe_stdio_server(server, timeout=args.timeout))

    if args.format == "json":
        print(
            json.dumps(
                {
                    "ok": _is_ok(findings, args.warnings_as_errors) and all(probe.ok for probe in probes),
                    "configs": [doc.to_dict() for doc in documents],
                    "findings": [finding.to_dict() for finding in findings],
                    "probes": [probe.to_dict() for probe in probes],
                },
                indent=2,
            )
        )
    else:
        _print_static_report(documents, findings)
        if has_blocking_errors(findings):
            print("\nProbe skipped because static errors were found.")
        else:
            _print_probe_report(probes)

    static_code = _exit_code(findings, args.warnings_as_errors)
    if static_code != 0:
        return static_code
    return 2 if any(not probe.ok for probe in probes) else 0


def _load_documents(paths: list[str]) -> list[ConfigDocument]:
    config_paths = discover_config_paths(paths)
    return [load_config(path) for path in config_paths]


def _all_static_findings(documents: list[ConfigDocument]) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    if not documents:
        findings.append(Finding("info", "no-configs-found", "No MCP config files were found.", Path.cwd()))
    for document in documents:
        findings.extend(run_static_checks(document))
    return tuple(findings)


def _all_servers(documents: list[ConfigDocument]) -> list[ServerSpec]:
    servers: list[ServerSpec] = []
    for document in documents:
        servers.extend(document.servers)
    return servers


def _is_ok(findings: tuple[Finding, ...], warnings_as_errors: bool) -> bool:
    if has_blocking_errors(findings):
        return False
    if warnings_as_errors and any(finding.severity == "warning" for finding in findings):
        return False
    return True


def _exit_code(findings: tuple[Finding, ...], warnings_as_errors: bool) -> int:
    return 1 if not _is_ok(findings, warnings_as_errors) else 0


def _print_static_report(documents: list[ConfigDocument], findings: tuple[Finding, ...]) -> None:
    server_count = sum(len(document.servers) for document in documents)
    errors = sum(1 for finding in findings if finding.severity == "error")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    info = sum(1 for finding in findings if finding.severity == "info")
    print(f"mcp-server-doctor checked {len(documents)} config file(s), {server_count} server(s)")
    print(f"errors={errors} warnings={warnings} info={info}")

    if documents:
        print("\nConfigs:")
        for document in documents:
            print(f"  - {document.path}")
            for server in document.servers:
                print(f"    - {server.name} ({server.transport})")

    if findings:
        print("\nFindings:")
        for finding in findings:
            target = f"{finding.path}"
            if finding.server:
                target += f"#{finding.server}"
            print(f"  [{finding.severity}] {target} {finding.code}: {finding.message}")
            if finding.hint:
                print(f"    hint: {finding.hint}")


def _print_probe_report(probes: list[ProbeResult]) -> None:
    if not probes:
        print("\nNo servers selected for probe.")
        return
    print("\nProbes:")
    for probe in probes:
        status = "ok" if probe.ok else "failed"
        print(f"  [{status}] {probe.server.name}: {probe.message}")
        if probe.capabilities:
            print(f"    capabilities: {', '.join(probe.capabilities)}")
        if probe.tools:
            print(f"    tools: {', '.join(probe.tools)}")
        if probe.stderr_tail and not probe.ok:
            print("    stderr:")
            for line in probe.stderr_tail:
                print(f"      {line}")
