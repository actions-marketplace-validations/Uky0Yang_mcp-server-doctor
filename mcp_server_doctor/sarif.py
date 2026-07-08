from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .models import Finding, ProbeResult


RULE_DESCRIPTIONS = {
    "broad-docker-volume": "Docker volume mounts should use narrow host paths.",
    "command-not-found": "Configured MCP command must exist on PATH.",
    "command-path-not-found": "Configured MCP command path must exist.",
    "config-encoding": "MCP config files must be UTF-8.",
    "config-not-found": "The requested MCP config file must exist.",
    "config-root": "MCP config root must be a JSON object.",
    "cwd-not-directory": "Configured cwd must be a directory.",
    "cwd-not-found": "Configured cwd must exist.",
    "invalid-args": "MCP server args must be a list of strings.",
    "invalid-command": "MCP server command must be a string.",
    "invalid-cwd": "MCP server cwd must be a string.",
    "invalid-env": "MCP server env must be a string map.",
    "invalid-json": "MCP config files must be valid JSON.",
    "invalid-mcpServers": "mcpServers must be an object.",
    "invalid-server": "Each MCP server config must be an object.",
    "invalid-server-name": "MCP server names must be non-empty strings.",
    "invalid-url": "Remote MCP server url must be a string.",
    "literal-secret-env": "MCP config env values should not contain literal secrets.",
    "missing-mcpServers": "MCP config must include an mcpServers object.",
    "missing-transport": "MCP servers must define a local command or remote url.",
    "remote-server": "Remote MCP servers are only statically checked.",
    "secret-arg": "MCP config args must not contain token-like values.",
    "secret-value": "MCP config env values must not contain token-like values.",
    "shell-wrapper": "MCP servers should avoid shell execution wrappers.",
    "unpinned-package": "Package-runner MCP commands should pin package versions.",
}


def build_sarif(
    findings: tuple[Finding, ...],
    probes: list[ProbeResult] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    probes = probes or []
    reportable_findings = tuple(finding for finding in findings if finding.severity != "info")
    rule_ids = {finding.code for finding in reportable_findings}
    rule_ids.update(_probe_rule_id(probe) for probe in probes if not probe.ok)
    rules = [_rule(rule_id) for rule_id in sorted(rule_ids)]

    results: list[dict[str, Any]] = []
    results.extend(_finding_result(finding, root) for finding in reportable_findings)
    results.extend(_probe_result(probe, root) for probe in probes if not probe.ok)

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "mcp-server-doctor",
                        "informationUri": "https://github.com/Uky0Yang/mcp-server-doctor",
                        "version": __version__,
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }


def _rule(rule_id: str) -> dict[str, Any]:
    description = RULE_DESCRIPTIONS.get(rule_id, rule_id.replace("-", " "))
    return {
        "id": rule_id,
        "name": rule_id,
        "shortDescription": {"text": description},
        "helpUri": "https://github.com/Uky0Yang/mcp-server-doctor#what-it-checks",
    }


def _finding_result(finding: Finding, root: Path | None) -> dict[str, Any]:
    message = finding.message if not finding.hint else f"{finding.message} Hint: {finding.hint}"
    if finding.server:
        message = f"{finding.server}: {message}"
    return {
        "ruleId": finding.code,
        "level": _level(finding.severity),
        "message": {"text": message},
        "locations": [_location(finding.path, root)],
    }


def _probe_result(probe: ProbeResult, root: Path | None) -> dict[str, Any]:
    return {
        "ruleId": _probe_rule_id(probe),
        "level": "error",
        "message": {"text": f"{probe.server.name}: {probe.message}"},
        "locations": [_location(probe.server.path, root)],
    }


def _probe_rule_id(probe: ProbeResult) -> str:
    if "Timed out" in probe.message:
        return "probe-timeout"
    if "non-JSON" in probe.message:
        return "probe-non-json-stdout"
    if "initialize returned error" in probe.message:
        return "probe-initialize-error"
    if "tools/list returned error" in probe.message:
        return "probe-tools-list-error"
    if "Failed to start" in probe.message or "Process start failed" in probe.message:
        return "probe-start-failed"
    return "probe-failed"


def _location(path: Path, root: Path | None) -> dict[str, Any]:
    uri = _uri(path, root)
    return {"physicalLocation": {"artifactLocation": {"uri": uri}}}


def _uri(path: Path, root: Path | None) -> str:
    try:
        if root:
            return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        pass
    return path.as_posix()


def _level(severity: str) -> str:
    if severity == "error":
        return "error"
    if severity == "warning":
        return "warning"
    return "note"
